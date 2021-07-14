import json
import math

import numpy
import talib
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from strategy import BaseStrategy, Signal
from termcolor import colored, cprint
from util import trades_to_ohlc, reformat_ohlc, interval_dt


class ParabolicSAR(BaseStrategy):
    intraday_only = False
    arr_lo = []
    arr_hi = []

    def __init__(self, **params):
        super().__init__()
        self.historical_short = []
        self.historical_last_ts = None
        self.indicator_data = [{"ind": 0, "mid": 0, "timestamp": datetime.now()}]

        self.interval_size = params.pop("interval")
        self.length = params.pop("length", 100)
        self.min_length = 10

        self.sar = [0]

        self.cur = None

    def __str__(self):
        return f"<ParabolicSAR length={self.length}>"

    def update_trades(self, trade: dict) -> None:
        """
        Добавить новые сделки к историческим данным.

        historical — это список OHLC по интервалам.
        Интервалы создаются, даже если в этот период не было сделок.
        """
        trades_by_interval = defaultdict(list)

        # Смикшировать последний интервал и новую сделку
        if self.historical:
            last_known_interval = self.historical.pop()
            ts = last_known_interval["timestamp"]
            # print("last_known_interval TS:", ts)
            trades_by_interval[ts] = [
                {"price": last_known_interval["open"], "size": "1"},
                {"price": last_known_interval["high"], "size": "1"},
                {"price": last_known_interval["low"], "size": "1"},
                {"price": last_known_interval["close"], "size": "1"},
            ]

        dt = interval_dt(trade) + timedelta(minutes=30)
        ts_q = math.ceil(dt.timestamp()) // self.interval_size
        ts_r = int(ts_q * 1000 * self.interval_size)
        trades_by_interval[ts_r].append(trade)

        ohlc_by_interval = list(map(trades_to_ohlc, trades_by_interval.items()))

        self.add_to_historical(ohlc_by_interval)

        low = numpy.array([float(d["low"]) for d in self.historical_short])
        high = numpy.array([float(d["high"]) for d in self.historical_short])

        self.sar = talib.SAR(high, low, acceleration=0.02, maximum=5.0)

    def add_to_historical(self, data):
        for interval_ohlc in data:
            ts = interval_ohlc["timestamp"]
            if self.historical_last_ts == ts:
                # заменить последний интервал
                self.historical_short[-1] = interval_ohlc
            else:
                # добавить новый интервал
                self.historical_short.append(interval_ohlc)
                self.historical_last_ts = ts

        # # Пересчитывать len_lo и len_hi оптимальным образом
        if len(self.historical_short) > self.length:
            removed_historical = self.historical_short.pop(0)

        self.historical += data

    def test_price(self, dt: datetime, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после регистрации сделки.
        """
        signal = Signal.PASS

        data_len = len(self.historical_short)
        if data_len < self.min_length:
            # cprint(f"PASS: lack of data, {data_len} < {self.min_length}", "yellow")
            return signal

        price_to_compare = self.historical_short[-2]["close"]

        if price_to_compare < self.sar[-1]:
            signal = Signal.SHORT
        else:
            signal = Signal.LONG

        # if signal.value and self.cur != signal.value:
        #     txt = f"{dt:%Y-%m-%d %H:%M:%S} "
        #     txt += colored(f" Price: {price:0.4f} ", attrs=["reverse"])
        #     txt += f" SAR: {self.sar[-1]:0.4f} • Len: {len(self.historical_short)} • "
        #     txt += colored(f"{signal.value}", signal.color)
        #     print(txt)
        #     self.cur = signal.value

        return signal
