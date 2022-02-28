from .base import BaseExchange
from .backtest import BacktestExchange
from .ib2 import IBFakeExchange
from .ib_web import IBWebExchange


all_exchanges = {
    "BacktestExchange": BacktestExchange,
    "IBFakeExchange": IBFakeExchange,
    "IBWebExchange": IBWebExchange,
}

__all__ = [
    "BaseExchange",
    "BacktestExchange",
    "IBFakeExchange",
    "IBWebExchange",
    "all_exchanges",
]
