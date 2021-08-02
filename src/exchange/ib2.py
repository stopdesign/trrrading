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


class IBFakeExchange(BaseExchange, FakeStream, Healthcheck):
    fake_stream_url = "http://127.0.0.1:8080/trades/"

    def __init__(self, advisors: list, **kwargs):
        super().__init__(advisors)

        self.loop = asyncio.get_event_loop()
        nest_asyncio.apply(self.loop)

        self.ib = ib.IB()
        self.account = "DU1492107"

        # Подписаться на события, приходящие с биржи.
        self.ib.connectedEvent += self.on_connect
        self.ib.disconnectedEvent += self.on_disconnect
        self.ib.pendingTickersEvent += self.market_stream_event

        self.ib_params = {
            "host": "127.0.0.1",
            "port": 7497,  # 4001
            "clientId": 0,
            "timeout": 10,
        }

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
        self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")
        self.symbols = list(set([a.instrument for a in self.advisors]))
        self.all_data = pd.DataFrame()
        self.dt_last = None

        self.finished = False

    def on_connect(self):
        cprint(f"\nON_CONNECT, finished: {self.finished}", "green")

    def on_disconnect(self):
        cprint(f"\nON_DISCONNECT, finished: {self.finished}", "red")

    def do_healthcheck(self):
        cprint("do_healthcheck", "white")

    async def initial_update(self):
        summary = await self.ib.accountSummaryAsync(self.account)
        values = [v for v in summary if v.tag == 'NetLiquidation']

        print("\n1. NetLiquidation:", values[0].value)

        print("\n2. Positions:")
        for p in self.ib.positions():
            print(
                f"\t{p.contract.symbol:<5}",
                f"{p.position:>5}",
                f"{p.avgCost:8.2f}",
            )

        print("\n3. Trades:")
        for t in self.ib.trades():
            print(
                f"\t{t.contract.symbol:<5}",
                f"{t.order.action:<5}",
                f"{t.order.totalQuantity:>5} ",
                f"{t.orderStatus.status:<10}",
                t.order.outsideRth,
            )
        print()

    def load_data(self):
        df = load_many(self.symbols, ["TRADES", "BIDASK"], start=self.dt_from.date())
        # BIDASK должен приходить раньше TRADES для этого интервала
        return df.sort_values(["date", "ticker", "data_type"])

    def warm_up(self):
        """
        Прогнать события по историческим данным.
        """
        contracts = []
        for symbol in self.symbols:
            sym, pe = symbol.split(".")
            contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)
            contracts.append(contract)
        self.contracts = contracts

        self.all_data = self.load_data()

        stream = self.all_data.loc[self.dt_from: self.dt_start]
        for row in stream.itertuples():
            self.historical_stream_event(row)

    def start_listen(self):
        # Healthcheck в отдельном потоке
        task = asyncio.to_thread(self.healthcheck_loop)
        asyncio.gather(task, return_exceptions=True)

        # Поддерживать соединение и подписки на данные
        self.loop.create_task(self.connection_keeper())

        # Интервальные события
        self.loop.create_task(self.metronom())

        # Фейковая биржа
        params = {
            "symbol": "SPY.ARCA",
            "price": "438.50",
        }
        self.loop.create_task(self.fake_stream(self.fake_stream_url, params))

        self.loop.run_forever()

    def stop_listen(self):
        self.finished = True

        self.close_all()

        sleep(0.5)

        if self.ib.isConnected():
            self.ib.disconnect()

    async def connection_keeper(self):
        """
        Старается обеспечить постоянное соединение.
        """
        while not self.finished:
            # cprint("isConnected?", "white")
            if not self.ib.isConnected():
                cprint(" reConnect ", "yellow", attrs=["reverse"])
                try:
                    # Если в процессе коннекта event loop будет прерван
                    # больше чем на timeout, то всё сломается и придется
                    # перезапускать TWS/IBGateway.
                    res = await self.ib.connectAsync(**self.ib_params)
                    cprint(f"reConnect res: {res}")

                    #################################
                    # Подписка на обновления от IB
                    # await self.ib.qualifyContractsAsync(*contracts)
                    cprint(f"Start listening for TWS events", "blue")
                    for contract in self.contracts:
                        # Тиковые данные
                        self.ib.reqMktData(contract)

                        # Интервальные данные (Зачем?)
                        bars = self.ib.reqHistoricalData(
                            contract,
                            endDateTime='',
                            # Достаточно, чтобы заполнить пробел между
                            # историческими данными и real-time данными.
                            durationStr='300 S',
                            barSizeSetting='1 min',
                            whatToShow='TRADES',
                            useRTH=False,
                            formatDate=2,
                            keepUpToDate=True
                        )
                        c = contract
                        bars.updateEvent += lambda a, b: self.on_bar_update(a, b, c)
                    #################################

                except asyncio.exceptions.TimeoutError:
                    cprint("reConnection TimeoutError", "red")
                except ConnectionRefusedError:
                    cprint("reConnection ConnectionRefusedError", "red")
            await asyncio.sleep(1)

    def historical_stream_event(self, row):
        dt = row.Index.to_pydatetime()
        symbol = row.ticker

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
        # print()
        # cprint(f" ON_PENDING_TICKERS ", "yellow", attrs=["reverse"])

        # Обработать quotes
        for ticker in tickers:
            symbol = f"{ticker.contract.symbol}.{ticker.contract.primaryExchange}"
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            ask = ticker.ask if ticker.ask > 0 else None
            bid = ticker.bid if ticker.bid > 0 else None
            if ask or bid:
                payload = BidAsk(bid=bid, ask=ask)
                self.on_event("quote", dt, symbol, payload)
            await asyncio.sleep(0)

        # Обработать trades
        for ticker in tickers:
            symbol = f"{ticker.contract.symbol}.{ticker.contract.primaryExchange}"
            dt = ticker.time.replace(microsecond=0, tzinfo=None)
            for tick in ticker.ticks:
                if tick.tickType in TRADE_TYPES and tick.price > 0:
                    payload = Trade(price=tick.price, volume=tick.size)
                    self.on_event("trade", dt, symbol, payload)
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
            dt = datetime.utcnow()
            if dt.minute != prev_dt.minute:
                # norm_dt = dt.replace(second=0, microsecond=0)
                # Собрать все бары и запустить событие
                print()
                cprint(" ON_METRONOM ", "green", attrs=["reverse"])
            self.last_event["metronom"] = datetime.utcnow()
            await asyncio.sleep(0.1)
            prev_dt = dt

    async def on_bar_update(self, bars, has_new_bar, contract):
        symbol = f"{contract.symbol}.{contract.primaryExchange}"

        if bars:
            av = bars[-1].average
            color = "green" if has_new_bar else "yellow"
            dt = datetime.utcnow().replace(microsecond=0)
            cprint(f"{dt}: ON_BAR, {symbol}, price: {av:0.2f}", color)

        # После появления нового бара отправить событие
        if has_new_bar and len(bars) > 1:
            # The last closed bar
            bar = bars[-2]
            bar_dt = bar.date.replace(tzinfo=None)
            payload = Bar.from_bar_data(bar, symbol)
            self.on_event("bar", bar_dt, symbol, payload)

    def close_all(self):
        """
        Закрыть все открытые позиции.
        """
        for symbol, position in self.positions.items():
            amount = position["amount"]
            if amount > 0:
                self.trade("sell", abs(amount), symbol, self.dt_last)
            if amount < 0:
                self.trade("buy", abs(amount), symbol, self.dt_last)

    def trade(self, side, amount, symbol, dt):
        """
        Открыть позицию/ордер на бирже.
        """
        amount = 3.0
        cprint(f"TRADE: {side} {symbol} {amount}", color="cyan")

        sym, pe = symbol.split(".")
        contract = ib.Stock(sym, "SMART", "USD", primaryExchange=pe)

        # Добываю цену и делаю запас
        mid_price = self.get_price(symbol, "mid")
        lmt_price = mid_price
        if side == "sell":
            lmt_price -= lmt_price / 100 * 0.5
        if side == "buy":
            lmt_price += lmt_price / 100 * 0.5
        lmt_price = float(Decimal(lmt_price).quantize(Decimal("0.01")))

        order = ib.LimitOrder(side.upper(), amount, lmt_price, outsideRth=True)
        trade = self.ib.placeOrder(contract, order)

        while not trade.isDone():
            # cprint(trade.orderStatus, "white")
            cprint(f"orderStatus: {trade.orderStatus.status}", "white")
            self.ib.waitOnUpdate()

        cprint(
            f" DONE TRADE: "
            f"{trade.orderStatus.status}, "
            f"{trade.orderStatus.avgFillPrice:0.2f}, "
            f"mid: {mid_price:0.2f} ",
            "green",
            attrs=["reverse"]
        )
        print()

        # TODO: вызвать after_trade

        return None, amount

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            mid = Decimal(self.get_price(symbol, "mid")) - self.fee_rate
            total_value += position["amount"] * (mid - position["price"])
        return total_value
