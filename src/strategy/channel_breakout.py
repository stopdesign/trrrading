from decimal import Decimal
from strategy import BaseStrategy, Signal
from termcolor import colored, cprint


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

    def anal(self, data):
        """
        Анализ исторических данных.
        Находит локальные минимум и максимум на интервале.
        """
        # FIXME: не сработает на intraday
        if len(data) < self.min_length:
            return None, None

        return self.len_lo, self.len_hi

    # TODO: test_price VS test_time
    def test(self, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после регистрации сделки.
        """
        signal = Signal.PASS

        len_lo, len_hi = self.anal(self.historical_short)

        # Это стратегия
        if len_lo and len_hi:
            if price < len_lo:
                signal = Signal.SHORT
            elif price > len_hi:
                signal = Signal.LONG

        txt = colored(f" Test price: {price:0.4f} ", attrs=["reverse"])
        txt += f" len_lo: {len_lo}, len_hi: {len_hi},"
        txt += f" len: {len(self.historical_short)}, signal: {signal}"
        print(txt)

        return signal
