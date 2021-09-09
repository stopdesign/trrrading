from .signal import Signal
from .base import BaseStrategy
from .random import Random
from .channel_breakout_3 import ChannelBreakout3
from .channel_breakout_4 import ChannelBreakout4

all_strategies = {
    "Random": Random,
    "ChannelBreakout3": ChannelBreakout3,
    "ChannelBreakout4": ChannelBreakout4,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "all_strategies",
]
