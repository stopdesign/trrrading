from data_types import Bar
from datetime import timezone


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class BaseIndicator:
    def __init__(self, *args, **kwargs):
        self.value = {}
        self.values = []
        self.values_by_ts = {}
        self.init(*args, **kwargs)

    def init(self, *args, **kwargs):
        raise NotImplementedError

    def on_bar(self, bar: Bar):
        raise NotImplementedError

    def add_bar(self, bar: Bar):
        self.value = self.on_bar(bar)
        ts = dt_to_ts(bar.date)
        # self.value["ts"] = dt_to_ts(bar.date)
        # self.value["symbol"] = bar.symbol
        self.values.append(self.value)
        self.values_by_ts[ts] = self.value
