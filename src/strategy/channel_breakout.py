from datetime import datetime
from decimal import Decimal
from strategy import BaseStrategy, Signal
from termcolor import colored


class ChannelBreakout(BaseStrategy):
    intraday_only = False
    arr_lo = []
    arr_hi = []

    def __init__(self, **params):
        super().__init__()
        self.historical_short = []
        self.historical_last_ts = None

        self.length = params.get("length", 250)
        self.min_length = params.get("min_length", 30)

        # локальные минимумы/максимумы последнего интервала
        self.len_lo = Decimal("Infinity")
        self.len_hi = Decimal("-Infinity")

    def __str__(self):
        return f"<ChannelBreakout length={self.length}>"

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

        # Пересчитывать len_lo и len_hi оптимальным образом
        if len(self.historical_short) > self.length:
            removed_historical = self.historical_short.pop(0)
            if removed_historical["low"] == self.len_lo:
                self.len_lo = Decimal("Infinity")
            if removed_historical["high"] == self.len_hi:
                self.len_hi = Decimal("-Infinity")

        if self.len_lo == Decimal("Infinity"):
            for interval in self.historical_short:
                if interval["low"] < self.len_lo:
                    self.len_lo = interval["low"]
        else:
            self.len_lo = min(self.len_lo, self.historical_short[-1]["low"])

        if self.len_hi == Decimal("-Infinity"):
            for interval in self.historical_short:
                if interval["high"] > self.len_hi:
                    self.len_hi = interval["high"]
        else:
            self.len_hi = max(self.len_hi, self.historical_short[-1]["high"])

        self.historical += data

    # TODO: test_price VS test_time
    def test_price(self, dt: datetime, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после регистрации сделки.
        """
        signal = Signal.PASS

        if len(self.historical_short) < self.min_length:
            return signal

        # Это стратегия
        if self.len_lo and self.len_hi:
            if price < self.len_lo:
                signal = Signal.SHORT
            elif price > self.len_hi:
                signal = Signal.LONG

        # if signal.value:
        #     txt = f"{dt:%Y-%m-%d %H:%M:%S} "
        #     txt += colored(f" Price: {price:0.4f} ", attrs=["reverse"])
        #     txt += f" [{self.len_lo:0.4f}, {self.len_hi:0.4f}] • "
        #     txt += f"Len: {len(self.historical_short)} • "
        #     txt += colored(f"{signal.value}", signal.color)
        #     print(txt)

        return signal
