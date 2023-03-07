from collections import namedtuple
from indicator.base import BaseIndicator


class BaseStrategy:

    def __init__(self, **kwargs):
        self.exchange = kwargs.pop("exchange")
        self.name = kwargs.pop("strategy", None)
        self.symbol = kwargs.get("symbol")
        self.length = kwargs.get("length")
        self.params = namedtuple(self.name, kwargs.keys())(*kwargs.values())
        self.data = []
        # self.prev_signal = Signal.PASS
        # self.prev_signal_dt = None
        self.warmed = False
        self.on_start()

    def __repr__(self):
        return str(self.params)
    
    @property
    def market_system(self):
        return f"{self.symbol}_{self.name}"

    @property
    def indicators(self):
        return filter(lambda a: isinstance(a, BaseIndicator), self.__dict__.values())

    def on_start(self):
        pass

    @property
    def info(self):
        return f"{self}, signal={self.prev_signal.value}, data_len={len(self.data)}"

    def on_bar(self, data):
        pass

    def on_quote(self, data):
        pass

    def on_trade(self, data):
        pass
