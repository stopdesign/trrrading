from random import choice
from data_types import Bar
from strategy import BaseStrategy, Signal


class Random(BaseStrategy):

    def on_bar(self, pandas_ohlc):
        bar = Bar.from_pandas(pandas_ohlc)

        if bar.volume == 0:
            return None

        self.data.append(bar)

        return bar

    def test_price(self, price: float) -> Signal:
        bar = self.data[-1] if self.data else None

        if not bar:
            return Signal.PASS

        if len(self.data) % self.params.get("length", 1) == 0:
            return choice([Signal.LONG, Signal.SHORT])
        else:
            return Signal.PASS
