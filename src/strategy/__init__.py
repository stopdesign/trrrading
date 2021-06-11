from .signal import Signal
from .base import BaseStrategy
from .channel_breakout import ChannelBreakout
from .ch2 import ChannelBreakout2

__all__ = ["Signal", "BaseStrategy", "ChannelBreakout", "ChannelBreakout2"]

all_strategies = {
    "ChannelBreakout": ChannelBreakout,
    "ChannelBreakout2": ChannelBreakout2,
}
