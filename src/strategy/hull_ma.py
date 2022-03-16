import math
from datetime import time
from talipp.indicators import WMA
from strategy import BaseStrategy, Signal, hint
from data_types import Bar, Trade


class HullMa(BaseStrategy):
    padding = 0
    n2ma_1 = None
    nma_1 = None
    n_1 = None

    def on_start(self):
        n_half = round(self.length / 2)
        n_sqrt = round(math.sqrt(self.length))

        self.n2ma_1 = WMA(n_half)
        self.nma_1 = WMA(self.length)
        self.n_1 = WMA(n_sqrt)

    @hint
    def on_bar(self, pandas_ohlc) -> Signal:

        if type(pandas_ohlc) == Bar:
            bar = pandas_ohlc
        else:
            bar = Bar.from_pandas(pandas_ohlc)

        if bar.date.time() < time(hour=14, minute=33):
            return Signal.PASS

        if bar.date.time() >= time(hour=20, minute=59):
            return Signal.PASS

        if bar.volume == 0:
            return Signal.PASS

        bar.up = None
        bar.dn = None

        if self.data:
            self.n2ma_1.add_input_value(2 * bar.close)
            self.nma_1.add_input_value(bar.close)

        if self.n2ma_1 and self.nma_1:
            diff_1 = self.n2ma_1[-1] - self.nma_1[-1]
            self.n_1.add_input_value(diff_1)

        if len(self.n_1) > 1:
            bar.up = self.n_1[-1]
            bar.dn = self.n_1[-2]

        self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, trade: Trade) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        if trade.date.time() < time(hour=14, minute=33):
            return Signal.PASS

        if trade.date.time() >= time(hour=20, minute=59):
            return Signal.PASS

        if bar.up > bar.dn + 0.0005:
            return Signal.LONG

        if bar.up < bar.dn - 0.0005:
            return Signal.SHORT

        return Signal.PASS
