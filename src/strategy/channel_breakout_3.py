from talipp.indicators import DonchianChannels
from strategy import BaseStrategy, Signal, Bar


class ChannelBreakout3(BaseStrategy):
    don = None

    def on_start(self):
        self.don = DonchianChannels(self.length)

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        self.don.add_input_value(pandas_ohlc)

        if self.don:
            bar.up = self.don[-1].ub
            bar.dn = self.don[-1].lb
        else:
            bar.up = None
            bar.dn = None

        self.data.append(bar)

    def test_price(self, price: float) -> Signal:
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not bar or not bar.dn:
            return Signal.PASS

        if price < bar.dn:
            return Signal.SHORT

        if price > bar.up:
            return Signal.LONG

        return Signal.PASS
