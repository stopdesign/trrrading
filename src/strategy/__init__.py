from .signal import Signal
from .base import BaseStrategy
from .channel_breakout_3 import ChBr
from .channel_breakout_4 import ChBrStop

all_strategies = {
    "ChBr": ChBr,
    "ChBrStop": ChBrStop,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "all_strategies",
]
