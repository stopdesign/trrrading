from trader.data_types import Bar
from datetime import timezone


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class BaseIndicator:
    def __init__(self, *args, **kwargs):
        self.value = {}
        self.values = []
        self.values_by_ts = {}
        # self.source = None
        self.source_version = None
        self.version = None
        print(f"BaseIndicator init. Args: {args}, KWargs: {kwargs}")
        self.init(*args, **kwargs)

    def init(self, source, **kwargs):
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
