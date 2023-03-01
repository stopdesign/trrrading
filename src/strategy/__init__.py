from .signal import Signal
from .base import BaseStrategy, hint
from .random import Random
from .channel_breakout_3 import ChBr
from .channel_breakout_4 import ChannelBreakout4
from .range import Range
# from .renko import Renko
from .mfm import MoneyFlowMultiplier
from .drei_ema import DreiEma
from .hull_ma import HullMa
from .brainstorm import Brainstorm
from .ch_br_spy import ChBrSpy
from .grain import Grain
from .open_spike import OpenSpike

all_strategies = {
    "Grain": Grain,
    "Random": Random,
    "ChBr": ChBr,
    "ChannelBreakout4": ChannelBreakout4,
    "Range": Range,
    # "Renko": Renko,
    "MoneyFlowMultiplier": MoneyFlowMultiplier,
    "DreiEma": DreiEma,
    "HullMa": HullMa,
    "Brainstorm": Brainstorm,
    "ChBrSpy": ChBrSpy,
    "OpenSpike": OpenSpike,
}

__all__ = [
    "Signal",
    "BaseStrategy",
    "all_strategies",
    "hint",
]
