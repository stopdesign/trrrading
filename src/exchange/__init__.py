from .base import BaseExchange
from .backtest import BacktestExchange
from .exante import ExanteExchange
from .ib2 import IBFakeExchange


all_exchanges = {
    "BacktestExchange": BacktestExchange,
    "ExanteExchange": ExanteExchange,
    "IBFakeExchange": IBFakeExchange,
}

__all__ = [
    "BaseExchange",
    "BacktestExchange",
    "ExanteExchange",
    "IBFakeExchange",
    "all_exchanges",
]
