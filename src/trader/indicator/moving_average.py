from talipp.indicators import SMA

from trader.data_types import Bar
from trader.exchange import Data

from .base import BaseIndicator


class MovingAverage(BaseIndicator):
    chart = {
        "ma": {"type": "line", "color": "blue"},
    }

    def __init__(
        self,
        source: Data,
        *,
        skip_extra_hours: bool = True,
        skip_zero_volume: bool = True,
        length: int = 10
    ):
        super().__init__(
            source,
            skip_extra_hours=skip_extra_hours,
            skip_zero_volume=skip_zero_volume,
            length=length,
        )

    def init(self, **kwargs):
        length = kwargs.get("length", 10)
        self.data = SMA(length)

    def on_bar(self, bar: Bar):
        skip = False

        if self.skip_extra_hours and not bar.rth:
            skip = True

        if self.skip_zero_volume and bar.volume == 0:
            skip = True

        # Добавить данные в индикатор
        if not skip:
            self.data.add_input_value(bar.close)

        return {
            "ma": self.data[-1] if self.data else None,
        }
