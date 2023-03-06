from collections import namedtuple
from typing import Optional
from .signal import Signal
from indicator.base import BaseIndicator


def hint(func):
    """
    Возвращает сигнал, если состояние изменилось.
    """
    def inner(obj, *args, **kwargs) -> Optional[Signal]:
        signal = func(obj, *args, **kwargs)
        if signal != Signal.PASS and obj.prev_signal != signal:
            obj.prev_signal = signal
            obj.prev_signal_dt = args[0].date
            return signal
        return None
    return inner


class BaseStrategy:

    def __init__(self, **kwargs):
        self.exchange = kwargs.pop("exchange")
        self.name = kwargs.pop("strategy", None)
        self.symbol = kwargs.get("symbol")
        self.length = kwargs.get("length")
        self.params = namedtuple(self.name, kwargs.keys())(*kwargs.values())
        self.data = []
        self.prev_signal = Signal.PASS
        self.prev_signal_dt = None
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

    @hint
    def on_bar(self, data) -> Signal:
        return Signal.PASS

    @hint
    def on_quote(self, data) -> Signal:
        return Signal.PASS

    @hint
    def on_trade(self, data) -> Signal:
        return Signal.PASS
