"""
Triple Exponential Hull Moving Average

THMA(close, length):
	wma(
		wma(close, length / 3) * 3 - wma(close, length / 2) - wma(close, length),
		length
	)
"""


"""
HMA(close, length):

	wma(
		2 * wma(close, length / 2) - wma(close, length),
		round(sqrt(length))
	)

"""


from talipp.indicators import EMA, HMA, SMA, WMA

from trader.data_types import Bar

from .base import BaseIndicator


class HullMA(BaseIndicator):
    chart = {
        "hma": {"type": "line", "color": "blue"},
    }

    def init(self, source, interval):
        self.source = source
        print("interval", interval)
        self.data = HMA(interval)

    def on_bar(self, bar: Bar):
        skip = False

        if not bar.rth:
            skip = True

        if bar.volume == 0:
            skip = True

        # При каких-то условиях добавить данные в индикатор
        if not skip:
            self.data.add_input_value(bar.close)

        return {
            "hma": self.data[-1] if self.data else None,
            "prev_hma": self.data[-3] if len(self.data) > 5 else None,
        }
