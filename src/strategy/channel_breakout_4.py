import math
import pandas as pd
from talipp.indicators import DonchianChannels
from talipp.ohlcv import OHLCV
from strategy import BaseStrategy, Signal
from data_types import Bar


class ChannelBreakout4(BaseStrategy):
    """
    Как ChannelBreakout3, только гэпы заполняются фейковыми барами.
    """
    don = None
    padding = 0
    count_bars = False

    def on_start(self):
        self.padding = self.params.get("padding", 0)
        self.count_bars = self.params.get("count_bars", False)
        self.don = DonchianChannels(self.length)

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        if self.data:
            gap = abs(self.data[-1].close - bar.open)
            prev_price = self.data[-1].close
            prev_date = self.data[-1].date
            if gap > 0.15:
                price = prev_price
                d_price = 0.005
                cnt = math.ceil(gap / d_price)
                cnt = min(cnt, 1500)
                num = 0
                for i in range(cnt):
                    bar = Bar.from_pandas(pandas_ohlc)

                    if bar.open > self.data[-1].close:
                        price += d_price
                    else:
                        price -= d_price

                    for ii in range(2):

                        ohlcv = OHLCV(
                            open=price,
                            high=price,
                            low=price,
                            close=price,
                        )

                        self.don.add_input_value(ohlcv)

                        if self.don:
                            bar.up = self.don[-1].ub
                            bar.dn = self.don[-1].lb
                        else:
                            bar.up = None
                            bar.dn = None

                        bar.open = price
                        bar.high = price + 0.01
                        bar.low = price - 0.01
                        bar.close = price

                        bar.date = prev_date + pd.Timedelta(seconds=num)
                        num += 1

                        self.data.append(bar)

        if self.count_bars:
            cnt = int(math.ceil(min(bar.barCount / self.count_bars, 20)))
        else:
            cnt = 1

        for i in range(cnt):
            self.don.add_input_value(pandas_ohlc)
            bar = Bar.from_pandas(pandas_ohlc)

            if self.don:
                bar.up = self.don[-1].ub
                bar.dn = self.don[-1].lb
            else:
                bar.up = None
                bar.dn = None

            self.data.append(bar)

        return bar

    def test_price(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        if price > bar.up - self.padding:
            return Signal.LONG

        if price < bar.dn + self.padding:
            return Signal.SHORT

        return Signal.PASS
