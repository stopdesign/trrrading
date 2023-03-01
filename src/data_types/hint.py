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
        symbol = self.symbol.split(".")[0]
        return (
            f"Hint({self.signal_dt}, "
            f"{symbol}, "
            f"{self.strategy.name}, "
            f"{self.signal.abbr}: {self.signal_price:6.2f})"
        )

    @property
    def symbol(self) -> str:
        return self.strategy.symbol
