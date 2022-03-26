from .signal import Signal
from .base import BaseStrategy, hint
from .random import Random
from .channel_breakout_3 import ChannelBreakout3
from .channel_breakout_4 import ChannelBreakout4
from .range import Range
# from .renko import Renko
from .mfm import MoneyFlowMultiplier
from .drei_ema import DreiEma
from .hull_ma import HullMa

all_strategies = {
    "Random": Random,
    "ChannelBreakout3": ChannelBreakout3,
    "ChannelBreakout4": ChannelBreakout4,
    "Range": Range,
    # "Renko": Renko,
    "MoneyFlowMultiplier": MoneyFlowMultiplier,
    "DreiEma": DreiEma,
    "HullMa": HullMa,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "all_strategies",
    "hint",
]
