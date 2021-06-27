from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .parabolic_sar import ParabolicSAR
from .volty import Volty

all_strategies = {
    "ChannelBreakout": ChannelBreakout,
    "ParabolicSAR": ParabolicSAR,
    "Volty": Volty,
}

__all__ = [
    "Signal",
    "Volty",
    "BaseStrategy",
    "ChannelBreakout",
    "ParabolicSAR",
    "all_strategies",
]
