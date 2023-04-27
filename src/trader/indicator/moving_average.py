from talipp.indicators import SMA

from trader.data_types import Bar
from trader.exchange import Data
from trader.indicator import BaseIndicator


class MovingAverage(BaseIndicator):
    chart = {
        "ma": {"type": "line", "color": "blue"},
    }

    def __init__(
        self,
        source: Data,
        *,
        skip_extra_hours: bool = True,
        skip_empty: bool = True,
        length: int = 10
    ):
        super().__init__(
            source,
            skip_extra_hours=skip_extra_hours,
            skip_empty=skip_empty,
            length=length,
        )

    @property
    def ready(self):
        return bool(self.value.get("ma"))

    def init(self, **kwargs):
        length = kwargs.get("length", 10)
        self.data = SMA(length)

    def on_bar(self, bar: Bar):
        skip = False

        if self.skip_extra_hours and not bar.rth:
            skip = True

        if self.skip_empty and bar.volume == 0:
            skip = True

        # Добавить данные в индикатор
        if not skip:
            self.data.add_input_value(bar.close)

        return {
            "ma": self.data[-1] if self.data else None,
        }
