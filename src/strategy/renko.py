# df.reset_index(inplace=True)
# # df = df[['date', 'open', 'high', 'low', 'close']]
# # df
#
# renko = indicators.Renko(df)
#
# renko.brick_size = 0.19
# data = renko.get_ohlc_data()


import pandas as pd
from talipp.indicators import DonchianChannels
from strategy import BaseStrategy, Signal
from data_types import Bar
from stocktrends import indicators


class Renko(BaseStrategy):
    don = None
    ddd = None
    renko = None

    def on_start(self):
        self.don = DonchianChannels(self.length)
        self.ddd = []
        self.renko = pd.DataFrame()

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        self.ddd.append(pandas_ohlc)
        df = pd.DataFrame(self.ddd[50:])
        if not df.empty:
            df["date"] = df["Index"]
            renko = indicators.Renko(df)
            renko.brick_size = 5.0
            self.renko = renko.get_ohlc_data()

            print(self.renko.tail(3))

        self.don.add_input_value(pandas_ohlc)

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

        # print(bar.date)

        # if price > bar.up:
        #     return Signal.LONG
        #
        # if price < bar.dn:
        #     return Signal.SHORT
        #
        # print(self.renko)

        if self.renko.empty:
            return Signal.PASS

        # print(self.renko.tail(1).uptrend.item())

        if self.renko.tail(1).uptrend.item():
            return Signal.LONG
        else:
            return Signal.SHORT

        # return Signal.PASS
