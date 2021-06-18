from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .ch2 import ChannelBreakout2
from .parabolic_sar import ParabolicSAR

all_strategies = {
    "ChannelBreakout": ChannelBreakout,
    "ChannelBreakout2": ChannelBreakout2,
    "ParabolicSAR": ParabolicSAR,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "ChannelBreakout",
    "ChannelBreakout2",
    "ParabolicSAR",
    "all_strategies",
]
