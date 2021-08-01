from .base import BaseExchange
from .backtest import BacktestExchange
from .exante import ExanteExchange
from .ib import InteractiveBrokersExchange
from .ib2 import IBFakeExchange


all_exchanges = {
    "BacktestExchange": BacktestExchange,
    "ExanteExchange": ExanteExchange,
    "InteractiveBrokersExchange": InteractiveBrokersExchange,
    "IBFakeExchange": IBFakeExchange,
}

__all__ = [
    "BaseExchange",
    "BacktestExchange",
    "ExanteExchange",
    "InteractiveBrokersExchange",
    "IBFakeExchange",
    "all_exchanges",
]
