from talipp.indicators import SMA, EMA

from data_types import Bar

from .base import BaseIndicator


class MovingAverage(BaseIndicator):
    chart = {
        "ma": {"type": "line", "color": "blue"},
    }

    def init(self, length):
        self.data = SMA(length)

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
            "ma": self.data[-1] if self.data else None,
        }
