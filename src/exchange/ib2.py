import json
import asyncio
import nest_asyncio
import pandas as pd
import ib_insync as ib
from time import sleep
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import cprint
from storage.ib import load_many
from exchange import BaseExchange
from exchange.mixin import FakeStream, Healthcheck
from exchange.data_types import BidAsk, Trade, Bar
from ib_insync.ticker import TickerUpdateEvent  # noqa


# https://interactivebrokers.github.io/tws-api/tick_types.html
TRADE_TYPES = TickerUpdateEvent().trades()._tickTypes  # noqa
BID_TYPES = TickerUpdateEvent().bids()._tickTypes  # noqa
ASK_TYPES = TickerUpdateEvent().asks()._tickTypes  # noqa

BID_ASK_COLUMNS_MAP = {
    "open": "av_bid",
    "high": "max_ask",
    "low": "min_bid",
    "close": "av_ask",
}


class IBFakeExchange(BaseExchange, FakeStream, Healthcheck):
    fake_stream_url = "http://127.0.0.1:8080/trades/"
    healthcheck_interval = 60
    rel_price_cap = 0.02  # на столько limit price будет хуже mid_price
    price_precision = Decimal("0.01")

    def __init__(self, advisors: list, **kwargs):
        super().__init__(advisors)

        self.loop = asyncio.get_event_loop()
        nest_asyncio.apply(self.loop)

        self.ib = ib.IB()

        # Подписаться на события шлюза IB
        self.ib.connectedEvent += self.on_connect
        self.ib.disconnectedEvent += self.on_disconnect
        self.ib.pendingTickersEvent += self.market_stream_event
        self.ib.errorEvent += self.on_ib_error
        self.ib.timeoutEvent += lambda *args: cprint(f"timeoutEvent: {args}", "yellow")

        self.ib_params = {
            "host": "127.0.0.1",
            "port": 4001,  # 7497
            "clientId": 0,
            "timeout": 10,
        }

        self._net_value = 0

        # Синхронно добыть параметры аккаунта:
        # баланс депозита, позиции, стоимость активов...
        try:
            self.ib.connect(**self.ib_params)
            future = asyncio.wait({self.initial_update()})
            done, _ = self.loop.run_until_complete(future)
        finally:
            self.ib.disconnect()

        self.contracts = []
        self.quotes = {}
        self.dt_start = kwargs.pop("dt_start")
        self.dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=5))
        # self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash_initial = self._net_value
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")
        self.symbols = list(set([a.instrument for a in self.advisors]))
        self.all_data = pd.DataFrame()
        self.dt_last = None

        self.finished = False
        self.subscribed = False

    def on_connect(self):
        cprint(f"\nON_CONNECT, finished: {self.finished}", "green")

    def on_disconnect(self):
        cprint(f"\nON_DISCONNECT, finished: {self.finished}", "red")

    def on_ib_error(self, req_id, error_code, error_string, contract):
        if req_id and req_id < 0:
            cprint(f"ON_ERROR: {req_id} {error_code} {error_string} {contract}", "red")

        # Отвалилась market data.
        # No market data during competing live session.
        if error_code == 10197:
            self.subscribed = False

        # Отвалилась подписка на bar updates
        # Failed to request live updates (disconnected).
        if error_code == 10182:
            self.subscribed = False

    def do_healthcheck(self):
        pass

    async def initial_update(self):
        summary = await self.ib.accountSummaryAsync()
        values = [v for v in summary if v.tag == "NetLiquidation"]

        self._net_value = Decimal(values[0].value)

        # Открытые ордеры
        if ot := self.ib.openTrades():
            print()
            for t in ot:
                symbol = f"{t.contract.symbol}.{t.contract.exchange}"
                symbol = symbol.replace(".SMART", ".ARCA")
                cprint(
                    f"{symbol:<12}"
                    f"{t.order.action:<5}"
                    f"{t.order.totalQuantity:>8} "
                    f"{t.orderStatus.status:<10}"
                    f"{t.order.outsideRth}",
                    "red",
                )
            print()

    def load_historical_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())
        # BIDASK должен приходить раньше TRADES для этого интервала
        return df.sort_values(["date", "ticker", "data_type"])

    def load_current_data(self, contract, data_type):
        bars = []
        data_type = data_type.replace("BIDASK", "BID_ASK")
        for i in range(10):
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="3 D",
                barSizeSetting="1 min",
                whatToShow=data_type,
                useRTH=False,
                formatDate=2,
                timeout=30,
            )
            if len(bars):
                break
        if len(bars) == 0:
            raise ValueError("Empty response")
        df = ib.util.df(bars)
        df["date"] = df["date"].dt.tz_localize(None)
        df = df.set_index("date")

        # Убрать нулевые объемы
        df = df.loc[df.volume != 0]

        # В режиме BID_ASK данные имеют другой смысл. Переименовать.
        if data_type == "BIDASK":
            df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)
            # Убрать записи, где не было изменений.
            # Запись для начала основной сессии (RTH) сохраняется.
            df = df.drop_duplicates(
                subset=["av_bid", "max_ask", "min_bid", "av_ask"],
                keep="first",
            )
        symbol = f"{contract.symbol}.{contract.exchange}"
        symbol = symbol.replace(".SMART", ".ARCA")
        df["ticker"] = symbol
        df["data_type"] = data_type

        return df

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """
        contracts = []
        for symbol in self.symbols:
            sym, pe = symbol.split(".")
            contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)
            contract.bars = None
            contract.mkt_ticker = None
            contracts.append(contract)
        self.contracts = contracts

        self.all_data = self.load_historical_data()

        cprint("\nGet real-time data", "white")
        current_data = []
        try:
            self.ib.connect(**self.ib_params)
            for symbol in self.symbols:
                sym, pe = symbol.split(".")
                contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)
                for data_type in ["TRADES", "BIDASK"]:
                    query = f"ticker == '{symbol}' & data_type == '{data_type}'"
                    tail_df = self.all_data.query(query)
                    last_dt = tail_df.tail(1).index.item().to_pydatetime()
                    df = self.load_current_data(contract, data_type)
                    df = df[df.index > last_dt]
                    current_data.append(df)
        finally:
            self.ib.disconnect()

        current_data.append(self.all_data)
        self.all_data = pd.concat(current_data)
        self.all_data = self.all_data.sort_values(["date", "ticker", "data_type"])

        # Прогнать события по историческим данным
        stream = self.all_data.loc[self.dt_from: self.dt_start]
        for row in stream.itertuples():
            self.historical_stream_event(row)

        # TODO: вынести отсюда куда-нибудь еще
        # Для каждого символа последние исторические данные должны быть
        # не позднее, чем 5 минут назад.
        now = datetime.utcnow().replace(microsecond=0)
        for symbol in self.symbols:
            quote_dt = self.quotes.get(symbol, {}).get("dt")
            if not quote_dt or now - quote_dt > timedelta(minutes=5):
                cprint(
                    f" DATA IS TOO OLD: {quote_dt} ",
                    color="red",
                    attrs=["reverse"],
                )

    def start_listen(self):
        # Healthcheck в отдельном потоке
        task = asyncio.to_thread(self.healthcheck_loop)
        asyncio.gather(task, return_exceptions=True)

        # Поддерживать соединение и подписки на данные
        self.loop.create_task(self.connection_keeper())

        # Интервальные события
        self.loop.create_task(self.metronom())

        self.loop.run_forever()

    def stop_listen(self):
        self.finished = True

        # Отменить все активные ордеры
        if self.ib.isConnected():
            self.ib.reqGlobalCancel()

        sleep(0.5)

        if self.ib.isConnected():
            self.ib.disconnect()

    async def connection_keeper(self):
        """
        Старается обеспечить постоянное соединение.
        """
        while not self.finished:
            if not self.ib.isConnected():
                self.subscribed = False
                try:
                    cprint(" reConnect ", "blue", attrs=["reverse"])
                    await self.ib.connectAsync(**self.ib_params)
                except asyncio.exceptions.TimeoutError:
                    cprint("reConnect TimeoutError", "red")
                except ConnectionRefusedError:
                    cprint("reConnect ConnectionRefusedError", "red")

            if not self.subscribed:
                await self.ib_resubscribe()

            await asyncio.sleep(1)

    def create_on_bar(self, symbol):
        async def func(a, b):
            return await self.on_bar_update(a, b, symbol)

        return func

    async def ib_resubscribe(self):
        """
        Подписка на обновления по контрактам.
        """
        if self.subscribed:
            return

        for contract in self.contracts:
            if contract.bars is not None:
                cprint(f"Cancel HD, {contract}", "red")
                self.ib.cancelHistoricalData(contract.bars)

            # Интервальные данные
            contract.bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                # Достаточно, чтобы заполнить пробел между
                # историческими данными и real-time данными.
                # TODO: учесть возможность восстановления соединения после паузы
                durationStr="600 S",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=2,
                keepUpToDate=True,
            )
            symbol = str(f"{contract.symbol}.{contract.primaryExchange}")
            contract.bars.updateEvent += self.create_on_bar(symbol)

        for contract in self.contracts:
            # Тиковые данные
            if contract.mkt_ticker:
                cprint(f"Cancel MKT, {contract}", "red")
                self.ib.cancelMktData(contract)
            contract.mkt_ticker = self.ib.reqMktData(contract)

        cprint(f"Started listening for IB events\n", "blue")

        self.subscribed = True

    def historical_stream_event(self, row):
        dt = row.Index.to_pydatetime()
        symbol = row.ticker

        # TODO: поставить RTH у payload

        if row.data_type == "BIDASK":
            payload = BidAsk(bid=row.av_bid, ask=row.av_ask)
            self.on_event("quote", dt, symbol, payload)

        if row.data_type == "TRADES":
            for price in [row.open, row.high, row.low, row.close]:
                payload = Trade(price=price, volume=row.volume)
                self.on_event("trade", dt, symbol, payload)
            self.on_event("bar", dt, symbol, row)

    async def fake_stream_event(self, data):
        data = json.loads(data.decode())

        dt = datetime.utcnow().replace(microsecond=0)
        self.dt_last = dt

        symbol = data["symbolId"]

        price = float(data["price"])
        volume = int(float(data["size"]))

        quote = BidAsk(bid=price - 0.02, ask=price + 0.02)
        self.on_event("quote", dt, symbol, quote)

        trade = Trade(price=price, volume=volume)
        self.on_event("trade", dt, symbol, trade)

        bar = Bar.from_fake_trade(
            ticker=symbol,
            date=dt,
            price=price,
            volume=volume,
        )
        self.on_event("bar", dt, symbol, bar)

    async def market_stream_event(self, tickers):
        # Обработать quotes
        for ticker in tickers:
            symbol = f"{ticker.contract.symbol}.{ticker.contract.primaryExchange}"
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            ask = ticker.ask if ticker.ask > 0 else None
            bid = ticker.bid if ticker.bid > 0 else None
            if ask or bid:
                payload = BidAsk(bid=bid, ask=ask)
                try:
                    self.on_event("quote", dt, symbol, payload)
                except Exception as e:
                    cprint(f"Exception [on_event quote]: {e}", "red")
            await asyncio.sleep(0)

        # Обработать trades
        for ticker in tickers:
            symbol = f"{ticker.contract.symbol}.{ticker.contract.primaryExchange}"
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            for tick in ticker.ticks:
                if tick.tickType in TRADE_TYPES and tick.price > 0:
                    payload = Trade(price=tick.price, volume=tick.size)
                    try:
                        self.on_event("trade", dt, symbol, payload)
                    except Exception as e:
                        cprint(f"Exception [on_event trade]: {e}", "red")
                await asyncio.sleep(0)
            await asyncio.sleep(0)

        # Лучше брать из ticker, но пока пусть так
        dt = datetime.utcnow().replace(microsecond=0)
        self.dt_last = dt

    async def metronom(self):
        """
        Запускает регулярные задачи.
        """
        prev_dt = datetime(2000, 1, 1)
        while not self.finished:
            dt = datetime.utcnow().replace(microsecond=0)
            if dt.minute != prev_dt.minute:
                self.on_event("minute", dt)
            self.last_event["metronom"] = datetime.utcnow()
            await asyncio.sleep(0.1)
            prev_dt = dt

    async def on_bar_update(self, bars, has_new_bar, symbol):
        """
        После появления нового бара отправить событие.

        TODO: Учесть, что при открытии приходит вчерашний BAR.

        TODO: Проверить, что нет разрывов в таймлайне.
        TODO: При необходимости отправить несколько баров.
        """
        if has_new_bar and len(bars) > 1:
            bar = bars[-2]  # The last closed bar
            bar_dt = bar.date.replace(tzinfo=None)
            payload = Bar.from_bar_data(bar, symbol)
            self.on_event("bar", bar_dt, symbol, payload)

    def trade(self, side, amount, symbol, dt):
        """
        Открыть позицию/ордер на бирже.
        """
        cprint(f" TRADE: {side} {symbol} {amount} ", color="cyan", attrs=["reverse"])

        sym, pe = symbol.split(".")
        contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)

        # Добываю цену и делаю запас
        mid_price = self.get_price(symbol, "mid")
        lmt_price = self.get_limit_price(mid_price, side)

        order = ib.LimitOrder(side.upper(), amount, lmt_price, outsideRth=True)

        self.check_margin(contract, order)

        # Размещаю ордер
        trade = self.ib.placeOrder(contract, order)

        # Жду исполнения ордера
        while not trade.isDone():
            cprint(f"orderStatus: {trade.orderStatus.status}", "white")
            self.ib.sleep(0.5)  # чтобы не вываливало 100500 строк сразу
            self.ib.waitOnUpdate(timeout=30)

        cprint(
            f" DONE TRADE: "
            f"{trade.orderStatus.status}, "
            f"{trade.orderStatus.avgFillPrice:0.2f}, "
            f"mid: {mid_price:0.2f}, "
            f"amnt: {amount:0.0f} ",
            color="green",
            attrs=["reverse"],
        )
        print()

        price = trade.orderStatus.avgFillPrice

        # Событие «успешное завершение сделки»
        payload = {
            "side": side,
            "amount": amount,
            "price": price,
            "profit": None,
        }
        self.on_event("after_trade", dt, symbol, payload)

        return price, amount

    def get_limit_price(self, mid_price, side):
        lmt_price = mid_price
        if side == "sell":
            lmt_price -= lmt_price * self.rel_price_cap
        if side == "buy":
            lmt_price += lmt_price * self.rel_price_cap
        lmt_price = float(Decimal(lmt_price).quantize(self.price_precision))
        return lmt_price

    def check_margin(self, contract, order):
        what_if = self.ib.whatIfOrder(contract, order)
        margin_after = max(
            float(what_if.initMarginAfter), float(what_if.maintMarginAfter)
        )
        cprint(
            f"commissionCurrency: {what_if.commissionCurrency}\n"
            f"minCommission: {float(what_if.minCommission):0.2f}\n"
            f"maxCommission: {float(what_if.maxCommission):0.2f}\n"
            f"margin_after: {margin_after:0.2f}",
            "white",
        )

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        return self._net_value

    def get_positions(self):
        positions = {}
        for p in self.ib.positions():
            symbol = f"{p.contract.symbol}.{p.contract.exchange}"
            positions[symbol] = {
                "amount": Decimal(p.position),
                "price": Decimal(p.avgCost),
            }
        self.positions = positions
        return self.positions

    def get_margin_level(self, short=False):
        return 0.3 if short else 0.25
