from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from strategy import Signal, BaseStrategy


@dataclass
class Hint:
    strategy: BaseStrategy
    signal: Signal
    signal_dt: datetime  # время срабатывания сигнала
    signal_price: Decimal

    def __repr__(self):
        return (
            f"Hint({self.symbol}, "
            f"{type(self.strategy).__name__}, "
            f"{self.signal.abbr}: {self.signal_price:0.2f}, "
            f"{self.signal_dt})"
        )

    @property
    def symbol(self) -> str:
        return self.strategy.symbol
