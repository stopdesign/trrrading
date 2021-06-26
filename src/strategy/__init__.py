from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .parabolic_sar import ParabolicSAR

all_strategies = {
    "ChannelBreakout": ChannelBreakout,
    "ParabolicSAR": ParabolicSAR,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "ChannelBreakout",
    "ParabolicSAR",
    "all_strategies",
]
