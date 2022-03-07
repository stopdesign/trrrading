from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from strategy import Signal, BaseStrategy


@dataclass
class Hint:
    symbol: str
    strategy: BaseStrategy
    signal: Signal
    signal_dt: datetime  # время срабатывания сигнала
    signal_price: Decimal
