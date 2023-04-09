import logging
from datetime import timezone

from trader.data_types import Bar
from trader.exchange.data import Data

log = logging.getLogger("indicator")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class BaseIndicator:
    # Настройки отображения индикатора
    chart = {}

    def __init__(
        self,
        source: Data,
        *,
        skip_extra_hours: bool = True,
        skip_zero_volume: bool = True,
        **kwargs,
    ):
        self.name = self.__class__.__name__
        self.source: Data = source
        self.skip_extra_hours = skip_extra_hours
        self.skip_zero_volume = skip_zero_volume
        self.kwargs = kwargs

        self.source_version = None
        self.version = None
        self.value = {}
        self.values = []
        self.values_by_ts = {}

        self.init(**kwargs)

    def __repr__(self) -> str:
        kwargs = ", ".join(f"{k}={v}" for k, v in self.kwargs.items())
        return f"{self.name}(source={self.source}, {kwargs})".replace(", )", ")")

    def init(self, **kwargs):
        pass

    def on_bar(self, bar: Bar):
        raise NotImplementedError

    def update_source(self, dt):
        """
        Проверить, обновился ли источник данных.
        При обновлении вызывается добавление бара в индикатор.
        """
        if self.source.bars:
            bar = self.source.bars[-1]
            ts = dt_to_ts(bar.date)
            if self.source_version != self.source.version:
                self.value = self.on_bar(bar)
                self.values.append(self.value)
                self.version = ts
                self.source_version = self.source.version
        self.values_by_ts[dt_to_ts(dt)] = self.value
