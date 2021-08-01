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


class IBFakeExchange(BaseExchange, FakeStream, Healthcheck):
    fake_stream_url = "http://127.0.0.1:8080/trades/"

    def __init__(self, advisors: list, **kwargs):
        super().__init__(advisors)

        self.loop = asyncio.get_event_loop()
        nest_asyncio.apply(self.loop)

        self.ib = ib.IB()
        self.account = "DU1492107"

        self.ib_params = {
            "host": "127.0.0.1",
            "port": 4001,  # 7497
            "clientId": 0,
            "timeout": 10,
        }

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

        # Подписаться на события, приходящие с биржи.
        self.ib.connectedEvent += self.on_connect
        self.ib.disconnectedEvent += self.on_disconnect
        self.ib.pendingTickersEvent += self.on_pending_tickers

        self.finished = False

    def on_connect(self):
        cprint(f"\nON_CONNECT, finished: {self.finished}", "green")

    def on_disconnect(self):
        cprint(f"\nON_DISCONNECT, finished: {self.finished}", "red")

    def on_pending_tickers(self, *args):
        cprint(f"\nON_PENDING_TICKERS: {args}", "yellow")

    def do_healthcheck(self):
        cprint("do_healthcheck", "white")

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

        self.loop.create_task(self.connection_keeper())

        # Фейковая биржа
        self.loop.create_task(self.fake_stream(self.fake_stream_url))

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
                cprint("reConnect", "yellow", attrs=["reverse"])
                try:
                    # Если в процессе коннекта event loop будет прерван
                    # больше чем на timeout, то всё сломается и придется
                    # перезапускать TWS/IBGateway.
                    res = await self.ib.connectAsync(**self.ib_params)
                    cprint(f"reConnect res: {res}")

                    #################################
                    # Подписка на обновления цен по контрактам
                    # await self.ib.qualifyContractsAsync(*contracts)
                    cprint(f"Start listening for TWS events", "blue")
                    for contract in self.contracts:
                        self.ib.reqMktData(contract)
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

        dt = datetime.now()
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

    def trade(self, side: str, amount: Decimal, symbol: str, dt: datetime):
        # start_amount = amount
        # trade_profit = None
        # position = self.positions.get(symbol, self.empty_position)
        # price = Decimal(self.get_price(symbol, side))

        cprint(" TRADE ", "red")

        # # Событие «успешное завершение сделки»
        # payload = {
        #     "side": side,
        #     "amount": start_amount,
        #     "price": price,
        #     "profit": trade_profit,
        # }
        # self.on_event("after_trade", dt, symbol, payload)

        return None, None

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
