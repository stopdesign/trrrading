from .signal import Signal
from .base import BaseStrategy
from .channel_breakout_3 import ChannelBreakout3

all_strategies = {
    "ChannelBreakout3": ChannelBreakout3,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "ChannelBreakout3",
    "all_strategies",
]
