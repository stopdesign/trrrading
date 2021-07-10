from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .parabolic_sar import ParabolicSAR
from .volty import Volty
from .dummy import Dummy
from .super_trend import SuperTrend

all_strategies = {
    "Dummy": Dummy,
    "ChannelBreakout": ChannelBreakout,
    "ParabolicSAR": ParabolicSAR,
    "Volty": Volty,
    "SuperTrend": SuperTrend,
}

__all__ = [
    "Dummy",
    "Signal",
    "Volty",
    "BaseStrategy",
    "ChannelBreakout",
    "ParabolicSAR",
    "SuperTrend",
    "all_strategies",
]
