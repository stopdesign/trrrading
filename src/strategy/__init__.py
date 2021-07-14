from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .channel_breakout_2 import ChannelBreakout2
from .parabolic_sar import ParabolicSAR
from .volty import Volty
from .dummy import Dummy
from .super_trend import SuperTrend

all_strategies = {
    "Dummy": Dummy,
    "ChannelBreakout": ChannelBreakout,
    "ChannelBreakout2": ChannelBreakout2,
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
    "ChannelBreakout2",
    "ParabolicSAR",
    "SuperTrend",
    "all_strategies",
]
