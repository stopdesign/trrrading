import asyncio
import nest_asyncio
import pandas as pd
import ib_insync as ib
import pandas_market_calendars as mcal
from time import sleep
from datetime import datetime, timedelta
from decimal import Decimal
from termcolor import cprint, colored
from notifications.alert import send_telegram
from nyse_cal import time_to_next_session, trading_session
from storage.ib import load_many
from exchange import BaseExchange
from exchange.mixin import Healthcheck
from exchange.data_types import BidAsk, Trade, Bar, Margin, Fee
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


class IBFakeExchange(BaseExchange, Healthcheck):
    healthcheck_interval = 60
    rel_price_cap = 0.005  # на столько limit price будет хуже mid_price
    price_precision = Decimal("0.01")

    margin = Margin(long=0.25, short=0.3)
    fee = Fee(fixed_price=1)

    def __init__(self, advisors: list, **kwargs):
        super().__init__(advisors)

        self.contracts = []

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

        # # Синхронно добыть параметры аккаунта:
        # # баланс депозита, позиции, стоимость активов...
        # try:
        #     self.ib.connect(**self.ib_params)
        #     future = asyncio.wait({self.initial_update()})
        #     done, _ = self.loop.run_until_complete(future)
        # finally:
        #     self.ib.disconnect()

        self.quotes = {}
        self.dt_start = kwargs.pop("dt_start")
        dt_from = kwargs.get("dt_from", self.dt_start - timedelta(days=10))
        self.dt_from = dt_from.replace(hour=0, minute=0, second=0)
        # self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash_initial = self._net_value
        self.cash = self.cash_initial
        self.symbols = list(set([a.instrument for a in self.advisors]))
        self.all_data = pd.DataFrame()
        self.dt_last = None

        self.finished = False
        self.subscribed = False

    def on_connect(self):
        cprint(f"ON_CONNECT, finished: {self.finished}", "green")
        send_telegram("ON_CONNECT")

    def on_disconnect(self):
        cprint(f"ON_DISCONNECT, finished: {self.finished}", "red")
        send_telegram("ON_DISCONNECT")
        self.subscribed = False
        for contract in self.contracts:
            if contract.mkt_ticker:
                cprint(f"Failed MKT: {contract.symbol}", "red")
                contract.mkt_ticker = None
            if contract.bars is not None:
                cprint(f"Failed BAR: {contract.symbol}", "red")
                contract.bars = None

    async def on_ib_error(self, req_id, error_code, error_string, contract):
        if req_id and req_id < 0 and "connection is OK" not in error_string:
            cprint(f"ON_ERROR: {req_id} {error_code} {error_string} {contract}", "red")

        # Отвалилась market data, MKT
        # No market data during competing live session.
        if error_code == 10197:
            for contract in self.contracts:
                cprint(f"Failed MKT: {contract.symbol}", "red")
                contract.mkt_ticker = None
            self.subscribed = False

        # Отвалилась подписка на BAR
        # 10182: Failed to request live updates (disconnected).
        # 162: Trading TWS session is connected from a different IP
        if error_code in [10182, 162]:
            n = 10
            while n > 0:
                n -= 1
                for contract in self.contracts:
                    if contract.bars is not None and contract.bars.reqId == req_id:
                        cprint(f"Failed BAR: {contract.symbol}", "red")
                        contract.bars = None
                        n = 0
                        break
                await asyncio.sleep(0.5)

    def do_healthcheck(self):
        if self.finished:
            return
        dt = datetime.utcnow().replace(microsecond=0)
        if not trading_session(dt):
            return
        txt = colored(f" healthcheck ", "white", attrs=["reverse"])
        print(f"{dt}: {txt}")
        for contract in self.contracts:
            if contract.last_bar:
                bar_age = (datetime.utcnow() - contract.last_bar)
                if bar_age > timedelta(minutes=3):
                    cprint(
                        f"HEALTH: old bar {contract.symbol}, {bar_age}",
                        color="red",
                        attrs=["reverse"],
                    )
            if contract.last_mkt:
                mkt_age = (datetime.utcnow() - contract.last_mkt)
                cprint(mkt_age, "cyan")

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

        # Узнать баланс депозита и всё такое
        future = asyncio.wait({self.initial_update()})
        done, _ = self.loop.run_until_complete(future)

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="3 D",
            barSizeSetting="1 min",
            whatToShow=data_type.replace("BIDASK", "BID_ASK"),
            useRTH=False,
            formatDate=2,
            timeout=30,
        )

        # Если после последнего бара прошло больше 100 секунд, то считаем его закрытым.
        # Это происходит при запросе данных за пределами торговой сессии.
        # В других случаях последний бар отрезается.
        last_bar_dt = bars[-1].date.replace(tzinfo=None)
        dt = datetime.utcnow().replace(microsecond=0)
        if dt - last_bar_dt < timedelta(seconds=100):
            bars = bars[:-1]

        df = ib.util.df(bars)
        df["date"] = df["date"].dt.tz_localize(None)
        df = df.set_index("date")

        # # Убрать нулевые объемы
        # df = df.loc[df.volume != 0]

        # РАЗМЕТИТЬ RTH
        start = datetime.utcnow() - timedelta(days=300)
        end = datetime.utcnow() + timedelta(days=1)
        cal_exchange = contract.primaryExchange.replace("ARCA", "NYSE")
        cal = mcal.get_calendar(cal_exchange).schedule(start, end)
        by_days = {}
        for day, t in sorted(cal.T.to_dict("list").items()):
            t0 = t[0].to_pydatetime()
            t1 = t[1].to_pydatetime()
            by_days[day.date()] = [t0.replace(tzinfo=None), t1.replace(tzinfo=None)]

        def is_main_session(dt):
            t0, t1 = by_days.get(dt.date(), (None, None))
            return str(int(t0 and t1 and t0 <= dt < t1))

        df["rth"] = df.index.map(is_main_session)

        # В режиме BID_ASK данные имеют другой смысл. Переименовать.
        if data_type == "BIDASK":
            df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)
            df = df.resample('1T').pad()

        if data_type == "TRADES":
            df1 = df.resample('1T').pad()

            df1["volume"] = df["volume"]
            df1["volume"].fillna("0", inplace=True)

            df1["barCount"] = df["barCount"]
            df1["barCount"].fillna("0", inplace=True)

            cols = ["open", "high", "low", "average"]
            df1.loc[df1['volume'] == "0", cols] = df1["close"]

            df1 = df1[(df1["barCount"] != "0") | (df1["rth"] == "1")]
            df = df1

        symbol = f"{contract.symbol}.{contract.exchange}"
        symbol = symbol.replace(".SMART", ".ARCA")
        df["ticker"] = symbol
        df["data_type"] = data_type

        return df

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """

        # Инициализировать IB-контракты для всех инструментов
        contracts = []
        for symbol in self.symbols:
            sym, pe = symbol.split(".")
            contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)
            contract.bars = None
            contract.mkt_ticker = None
            contract.last_bar = None
            contract.last_mkt = None
            contracts.append(contract)
        self.contracts = contracts

        # Загрузить исторические данные из файлов
        self.all_data = self.load_historical_data()

        cprint("Real-time data", "white")
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

        # Вычислить последний исторический бар для данного контракта
        for contract in self.contracts:
            symbol = f"{contract.symbol}.{contract.primaryExchange}"
            query = f"ticker == '{symbol}' & data_type == 'TRADES'"
            last_dt = stream.query(query).tail(1).index.item().to_pydatetime()
            contract.last_bar = last_dt
            cprint(f"{symbol:<10} last bar: {contract.last_bar}", color="white")

        # TODO: вынести отсюда куда-нибудь еще
        # Для каждого символа последние данные
        # о цене должны быть не старше 5 минут
        now = datetime.utcnow().replace(microsecond=0)
        for symbol in self.symbols:
            quote_dt = self.quotes.get(symbol, {}).get("dt")
            if not quote_dt or now - quote_dt > timedelta(minutes=5):
                cprint(
                    f" {symbol} outdated quotes: {quote_dt} ",
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

        self.loop.stop()

    async def connection_keeper(self):
        """
        Старается обеспечить постоянное соединение.
        """
        while not self.finished:
            dt = datetime.utcnow().replace(microsecond=0)

            time_to_next = time_to_next_session(dt, main=False)
            wake_up_in_advance = 60
            if time_to_next > timedelta(seconds=wake_up_in_advance):
                print()
                cprint(
                    f" Next trading session in {time_to_next}, sleep. ",
                    color="red",
                    attrs=["reverse"],
                )
                await asyncio.sleep(time_to_next.total_seconds() - wake_up_in_advance)
                continue

            if not self.ib.isConnected():
                self.subscribed = False
                try:
                    cprint(" reConnect ", "blue", attrs=["reverse"])
                    await self.ib.connectAsync(**self.ib_params)
                except asyncio.exceptions.TimeoutError:
                    cprint("reConnect TimeoutError", "red")
                except ConnectionRefusedError:
                    cprint("reConnect ConnectionRefusedError", "red")
            if self.ib.isConnected():
                await self.ib_resubscribe()
            await asyncio.sleep(5)

    def create_on_bar_handler(self, contract):
        async def func(a, b):
            return await self.on_bar_update(a, b, contract)

        return func

    async def ib_resubscribe(self):
        """
        Подписка на обновления по контрактам.
        """
        if not self.subscribed:
            for contract in self.contracts:
                # Тиковые данные
                if contract.mkt_ticker:
                    cprint(f"Cancel MKT: {contract.symbol}", "red")
                    self.ib.cancelMktData(contract)
                cprint(f"Subscribe MKT: {contract.symbol}", "blue")
                contract.mkt_ticker = self.ib.reqMktData(contract)
            self.subscribed = True

        for contract in self.contracts:
            if contract.bars is not None and contract.last_bar:
                dt = datetime.utcnow()
                if trading_session(dt) != "main":
                    # Не проверять непрерывность данных вне основной сессии.
                    continue
                bar_age = dt - contract.last_bar
                if bar_age > timedelta(minutes=3):
                    cprint(f"Cancel BAR (old): {contract.symbol}", "red")
                    self.ib.cancelHistoricalData(contract.bars)
                    contract.bars = None
                await asyncio.sleep(0)

        for contract in self.contracts:
            if contract.bars is None:
                cprint(f"Subscribe BAR: {contract.symbol}", "blue")
                # Подписка на интервальные данные.
                # С настройкой "2 D" ответ никогда не должен быть пустым
                contract.bars = self.ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    # Достаточно, чтобы заполнить пробел между
                    # историческими данными и real-time данными.
                    durationStr="2 D",  # два торговых дня, даже после выходных
                    barSizeSetting="1 min",
                    whatToShow="TRADES",
                    useRTH=False,
                    formatDate=2,
                    keepUpToDate=True,
                )
                contract.bars.updateEvent += self.create_on_bar_handler(contract)
                await self.on_bar_update(contract.bars, False, contract)

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

    async def on_bar_update(self, bars, _, contract):
        """
        После появления нового бара отправить событие.
        """
        symbol = str(f"{contract.symbol}.{contract.primaryExchange}")
        # Посмотреть, какой бар был последним, и добавить все новые бары
        for bar in bars[-1000:-1]:  # последние 1000, кроме самого последнего
            bar_dt = bar.date.replace(tzinfo=None)
            if bar_dt > contract.last_bar:
                payload = Bar.from_bar_data(bar, symbol)
                self.on_event("bar", bar_dt, symbol, payload)
                contract.last_bar = bar_dt
                await asyncio.sleep(0)

    def trade(self, side, amount, symbol, dt, tr_price):
        """
        Открыть позицию/ордер на бирже.
        """
        txt = f" TRADE: {side} {symbol} {amount} "
        cprint(txt, color="cyan", attrs=["reverse"])
        send_telegram(txt)

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
        prev_state = ""
        last_dt = datetime(1900, 1, 1)
        start_dt = datetime.utcnow().replace(microsecond=0)
        while not trade.isDone():
            dt = datetime.utcnow().replace(microsecond=0)
            cur_state = f"{trade.orderStatus.status} {trade.orderStatus.filled}"
            # Вывожу только изменения или обновления после долгой паузы
            if prev_state != cur_state or (dt - last_dt) > timedelta(seconds=10):
                if dt - last_dt > timedelta(seconds=1):
                    rem = float(amount) - trade.orderStatus.filled
                    sec = (dt - start_dt).total_seconds()
                    cprint(
                        f"{dt}  {symbol}  {trade.orderStatus.status:<13} "
                        f"{rem:5.0f} to fill, "
                        f"{sec:0.0f} sec",
                        "white"
                    )
                    last_dt = dt
            prev_state = cur_state
            try:
                self.ib.waitOnUpdate(timeout=30)
            except KeyboardInterrupt:
                cprint("waitOnUpdate has been interrupted", "red")
                self.stop_listen()
                return None, None

        dt = datetime.utcnow().replace(microsecond=0)
        sec = (dt - start_dt).total_seconds()
        txt = (
            f" DONE TRADE: "
            f"{trade.orderStatus.status}, "
            f"{trade.orderStatus.avgFillPrice:0.2f}, "
            f"mid: {mid_price:0.2f}, "
            f"amnt: {amount:0.0f}, "
            f"time: {sec:0.0f} "
        )
        cprint(txt, color="green", attrs=["reverse"])
        send_telegram(txt)

        price = trade.orderStatus.avgFillPrice

        # Событие «успешное завершение сделки»
        payload = {
            "side": side,
            "amount": amount,
            "price": price,
            "profit": None,
            "slippage": 0,  # TODO
            "fee": 0,  # TODO
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
        pass
        # what_if = self.ib.whatIfOrder(contract, order)
        # margin_after = max(
        #     float(what_if.initMarginAfter), float(what_if.maintMarginAfter)
        # )
        # cprint(
        #     f"commissionCurrency: {what_if.commissionCurrency}\n"
        #     f"minCommission: {float(what_if.minCommission):0.2f}\n"
        #     f"maxCommission: {float(what_if.maxCommission):0.2f}\n"
        #     f"margin_after: {margin_after:0.2f}",
        #     "white",
        # )

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
