import asyncio
from time import sleep

import pandas_market_calendars as mcal
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from termcolor import cprint
from exchange import BaseExchange
from history.ohlc_to_ticks import ohlc_to_trades
from util import interval_dt, parse_quote, load_from_ib_file, load_quotes_from_ib_file
from ib_insync import *
from ib_insync.ticker import TickerUpdateEvent


TRADE_TYPES = TickerUpdateEvent().trades()._tickTypes
BID_TYPES = TickerUpdateEvent().bids()._tickTypes
ASK_TYPES = TickerUpdateEvent().asks()._tickTypes


class InteractiveBrokersExchange(BaseExchange):
    def __init__(self, symbols: list, loop=None, **kwargs):  # noqa
        super().__init__(symbols)
        self.symbols = symbols
        self.fee_rate = Decimal("0.02")

        self.on_event = None

        self.loop = loop

        self.ib = IB()
        self.account = "DU1492107"

        self.ib.pendingTickersEvent += self.on_tick_event
        self.ib.disconnectedEvent += self.on_disconnect
        self.ib.updateEvent += self.on_update

        # self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.ib.connectAsync("127.0.0.1", 7497, clientId=0))

        self.cash_initial = self.net_value  # а смысл?
        self.cash = self.net_value
        self.positions = self.get_positions()

        print("self.cash_initial", self.cash_initial)

    def on_disconnect(self, *args, **kwargs):
        cprint(f"\non_disconnect: {args}, {kwargs}, finished: {self.finished}", "red")

    def on_update(self, *args, **kwargs):
        pass
        # cprint(f"\non_update: {args}, {kwargs}", "red")

    def start_listen(self, on_event, loop=None):
        self.on_event = on_event
        # self.loop = loop

        self.cash_initial = self.net_value  # а смысл?
        print("self.cash_initial 2", self.cash_initial)

        # task = asyncio.to_thread(self.healthcheck_loop)
        # asyncio.gather(task, return_exceptions=True)
        loop.create_task(self.metronom(on_event))
        loop.create_task(self.some_stream(on_event))

    def stop_listen(self, loop=None):
        self.finished = True
        if self.ib.isConnected():
            self.ib.disconnect()

    def process_historical_data(self, on_event):
        """
        Используется для наполнения историческими данными.
        Запускается синхронно.
        """
        now = datetime.utcnow()
        data = []
        for symbol in self.symbols:
            data += self.get_past_data(symbol, now, 60 * 25)  # подсчитать, сколько надо
        data = sorted(data, key=lambda x: x["timestamp"])

        for event in data:
            symbol = event.get("symbolId")

            if not symbol or "timestamp" not in event:
                continue

            dt = interval_dt(event)

            if "price" in event:
                on_event("historical_trade", dt, symbol, parse_quote(event))

            if "ask" in event:
                ask = list(map(parse_quote, event["ask"]))
                bid = list(map(parse_quote, event["bid"]))
                on_event("historical_quote", dt, symbol, {"ask": ask, "bid": bid})

    def get_past_data(self, symbol, before_dt, minutes):
        """
        Получить исторические данные.
        """
        exchange = symbol.split(".")[1]
        exchange = exchange.replace("ARCA", "NYSE")
        dt_from = self.count_back_trading_minutes(exchange, before_dt, minutes)

        cprint(f"Get past {symbol}, [{dt_from}, {before_dt}]")

        trades = self.get_historical_trades(symbol, days=1)

        cprint(f"Trades loaded: {len(trades)}")

        trades = ohlc_to_trades(trades)

        quotes = []
        for trade in trades:
            price = Decimal(trade["price"])
            quotes.append({
                "symbolId": symbol,
                "timestamp": trade["timestamp"],
                "ask": [{"price": price, "size": 100}],
                "bid": [{"price": price, "size": 100}],
            })
        return sorted(quotes + trades, key=lambda x: x["timestamp"])

    def count_back_trading_minutes(self, exchange, dt, minutes):
        """
        Отсчитывает minutes минут назад от dt
        с учетом рабочего расписания биржи.
        """
        cal = mcal.get_calendar(exchange)
        schedule = cal.schedule(start_date=dt - timedelta(days=20), end_date=dt)
        all_minutes = 0
        for day, t in sorted(schedule.T.to_dict("list").items(), reverse=True):
            t0 = t[0].to_pydatetime().replace(tzinfo=None)
            t1 = t[1].to_pydatetime().replace(tzinfo=None)
            t0, t1 = min(dt, t0), min(dt, t1)
            day_minutes = (t1 - t0).total_seconds() // 60
            if day_minutes and day_minutes + all_minutes >= minutes:
                return t1 - timedelta(minutes=minutes - all_minutes)
            all_minutes += day_minutes

    async def metronom(self, on_event):
        """
        В начале каждого интервала запускает обновление historical.
        """
        prev_dt = datetime(2000, 1, 1)
        while not self.finished:
            dt = datetime.utcnow()
            if dt.minute != prev_dt.minute:
                norm_dt = dt.replace(second=0, microsecond=0)
                # раз в минуту обновлять позиции
                self.get_positions()
                # on_event("before_interval", norm_dt)
            self.last_event["metronom"] = datetime.utcnow()
            await asyncio.sleep(1)
            prev_dt = dt

    def on_tick_event(self, tickers):
        for ticker in tickers:
            symbol = f"{ticker.contract.symbol}.{ticker.contract.primaryExchange}"
            dt = ticker.time.replace(tzinfo=None)
            bid = []
            ask = []

            for tick in ticker.ticks:
                data = parse_quote({
                    "price": str(tick.price),
                    "size": tick.size,
                })

                if tick.tickType in TRADE_TYPES:
                    self.on_event("trade", dt, symbol, data)
                if tick.tickType in BID_TYPES:
                    bid.append(data)
                if tick.tickType in ASK_TYPES:
                    ask.append(data)

            if bid or ask:
                self.on_event("quote", dt, symbol, {"ask": ask, "bid": bid})

    async def some_stream(self, on_event):
        """
        Подписка на стрим биржи.
        """
        min_delay = 0.5
        max_delay = 30
        delay = min_delay

        contracts = []
        for symbol in self.symbols:
            sym, pe = symbol.split(".")
            contract = Stock(sym, "SMART", "USD", primaryExchange=pe)
            contracts.append(contract)

        while not self.finished:
            cprint(f"Start listening for TWS events", "blue")
            # начать слушать

            # if not self.ib.isConnected():
            #     self.ib.connect("127.0.0.1", 4001, clientId=0)

            await self.ib.qualifyContractsAsync(*contracts)

            # подписаться на сделки
            for contract in contracts:
                self.ib.reqMktData(contract)

            # бесконечный цикл
            while not self.finished:
                await asyncio.sleep(1)

            # отписаться от сделок
            for contract in contracts:
                self.ib.cancelMktData(contract)

    def get_positions(self):
        res = {}
        for p in self.ib.positions(self.account):
            ticker = f"{p.contract.symbol}.{p.contract.exchange}"
            # if ticker in self.symbols:
            res[ticker] = {
                "amount": Decimal(p.position),
                "price": Decimal(str(p.avgCost)),
            }
        # import json
        # cprint(json.dumps(res, indent=2, default=str), "yellow")
        return res

    def get_cash_value(self):

        # future = asyncio.wait_for(future, timeout)
        # task = asyncio.ensure_future(future)

        t1 = self.loop.create_task(self.ib.accountSummaryAsync(self.account))
        res = asyncio.wait_for(t1, None)
        cprint(f">>>>> {res}", "red")

        # self.loop.create_task(self.ib.accountSummaryAsync(self.account))
        summary = self.loop.run_until_complete(self.ib.accountSummaryAsync(self.account))

        values = [v for v in summary if v.tag == 'TotalCashValue']
        if values:
            cash = Decimal(values[0].value)
            cprint(f"TotalCashValue: {cash}", "yellow")
            return cash
        else:
            return None

    @property
    def equity_value(self):
        summary = self.loop.run_until_complete(self.ib.accountSummaryAsync(self.account))

        values = [v for v in summary if v.tag == 'GrossPositionValue']
        if values:
            cash = Decimal(values[0].value)
            cprint(f"GrossPositionValue: {cash}", "yellow")
            return cash
        else:
            return None

    @property
    def net_value(self):
        # t1 = self.loop.create_task(self.ib.accountSummaryAsync(self.account))
        # res = asyncio.wait_for(t1, None)
        # cprint(f">>>>> {res}", "red")

        summary = self.loop.run_until_complete(self.ib.accountSummaryAsync(self.account))

        values = [v for v in summary if v.tag == 'NetLiquidation']
        if values:
            cash = Decimal(values[0].value)
            # cprint(f"NetLiquidation: {cash}", "yellow")
            return cash
        else:
            return None

    def get_data(self, symbol, day, data_type="TRADES", timeframe="1 min"):
        contract = Stock(symbol, "SMART", "USD", primaryExchange="ARCA")
        day_utc = datetime.combine(day, datetime.min.time()).replace(
            tzinfo=timezone.utc)
        day_utc = day_utc + timedelta(hours=27)  # +27H — чтобы закрыть весь день
        bars = []
        # if not self.ib.isConnected():
        #     self.ib.connect("127.0.0.1", 4001, clientId=0)
        for i in range(5):
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=day_utc,
                durationStr="1 D",
                barSizeSetting=timeframe,
                whatToShow=data_type,
                useRTH=False,
                formatDate=2,
                timeout=120,
            )
            if len(bars):
                break
        if len(bars) == 0:
            raise ValueError("Empty response")
        return util.df(bars)

    def get_historical_trades(self, ticker="COPX.ARCA", days=5):
        import pandas as pd
        import numpy as np

        symbol, exchange = ticker.split(".")

        today_utc = datetime.now(tz=timezone.utc).date()
        start = today_utc - timedelta(days=days)
        end = today_utc

        cprint(f"{ticker}, [{start}, {end}]", "blue")

        trades = []

        for day in daterange(start, end):

            # Получить данные за день
            try:
                df = self.get_data(symbol=symbol, day=day, data_type="TRADES")
            except ValueError:
                cprint(f"Empty response: {symbol}, {day}", "red")
                continue
            except ConnectionError as e:
                cprint(f"ConnectionError: {symbol}, {day}", "red")
                cprint(e, "red")
                continue

            # Пометить рабочие часы
            # df["rth"] = (df["date"] >= t0) & (df["date"] < t1)
            # df["rth"] = df["rth"].astype(int)

            df["symbolId"] = ticker
            df["date"] = df["date"].dt.tz_localize(None)
            df = df.set_index("date")
            df.sort_index(inplace=True)

            # Убрать нулевые объемы
            df = df.loc[df.volume != 0]

            df["timestamp"] = pd.to_datetime(df.index, utc=True).values.astype(np.int64) // 10 ** 6

            trades += df.to_dict(orient="records")

        return trades

    def trade(self, side: str, size: int, symbol: str):
        """
        Открыть позицию/ордер на бирже.
        """
        cprint(f"TRADE: {side} {symbol} {size}", color="cyan")

        assert side in ["buy", "sell"]

        sym, pe = symbol.split(".")
        contract = Stock(sym, "SMART", "USD", primaryExchange=pe)

        order = MarketOrder(side.upper(), size, outsideRth=True)
        print(order)
        trade = self.ib.placeOrder(contract, order)

        while not trade.isDone():
            cprint(trade.orderStatus, "white")
            cprint(f"orderStatus: {trade.orderStatus.status}", "yellow")
            # self.ib.waitOnUpdate()
            sleep(3)

        return None, size


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)
