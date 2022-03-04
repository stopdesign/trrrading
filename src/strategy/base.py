from datetime import datetime
from decimal import Decimal

import pandas as pd
from dataclasses import dataclass
from typing import Optional
from .signal import Signal


@dataclass
class Hint:
    symbol: str
    strategy: str
    signal: Signal
    # dt: datetime
    # signal_price: Decimal


def hint(func):
    """
    Преобразует сигнал в Hint, учитывая информацию о предыдущем состоянии.
    """
    def inner(obj, *args, **kwargs) -> Optional[Hint]:
        signal = func(obj, *args, **kwargs)
        if signal != Signal.PASS and obj.prev_signal != signal:
            strategy = type(obj).__name__
            obj.prev_signal = signal
            return Hint(symbol=obj.symbol, strategy=strategy, signal=signal)
        return None
    return inner


class BaseStrategy:

    def __init__(self, symbol, **kwargs):
        self.symbol = symbol
        self.length = kwargs.get("length")
        self.params = kwargs
        self.data = []
        self.prev_signal = Signal.PASS
        self.on_start()

    def __repr__(self):
        params = ""
        for key, value in self.params.items():
            params += f" {key}={value},"
        return f"{type(self).__name__}({params.strip().strip(',')})"

    def on_start(self):
        pass

    @hint
    def on_bar(self, data):
        pass

    @hint
    def on_quote(self, data) -> Signal:
        return Signal.PASS

    @hint
    def on_trade(self, data) -> Signal:
        return Signal.PASS
