import math
from datetime import time
from talipp.indicators import DonchianChannels
from strategy import BaseStrategy, Signal, hint
from data_types import Bar


class ChannelBreakout3(BaseStrategy):
    don = None
    padding = 0
    count_bars = False

    def on_start(self):
        self.padding = self.params.get("padding", 0)
        self.count_bars = self.params.get("count_bars", False)
        self.don = DonchianChannels(self.length)

    @hint
    def on_bar(self, pandas_ohlc) -> Signal:

        if type(pandas_ohlc) == Bar:
            bar = pandas_ohlc
        else:
            bar = Bar.from_pandas(pandas_ohlc)

        # if bar.date.time() < time(hour=13, minute=30):
        #     return Signal.PASS
        #
        # if bar.date.time() >= time(hour=19, minute=59):
        #     return Signal.PASS

        if bar.volume == 0:
            return Signal.PASS

        if self.count_bars:
            cnt = int(math.ceil(min(bar.barCount / self.count_bars, 20)))
        else:
            cnt = 1

        for i in range(cnt):
            self.don.add_input_value(pandas_ohlc)

            if self.don:
                bar.up = self.don[-1].ub
                bar.dn = self.don[-1].lb
            else:
                bar.up = None
                bar.dn = None

            self.data.append(bar)

        return Signal.PASS

    @hint
    def on_trade(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        # if bar.date.time() < time(hour=13, minute=35):
        #     return Signal.PASS
        #
        # if bar.date.time() >= time(hour=19, minute=55):
        #     return Signal.PASS

        if price > bar.up - self.padding:
            return Signal.LONG

        if price < bar.dn + self.padding:
            return Signal.SHORT

        return Signal.PASS
