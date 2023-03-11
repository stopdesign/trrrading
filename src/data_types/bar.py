from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class Bar:
    date: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = None
    rth: bool = None

    def __repr__(self):
        return f"Bar({self.symbol}, date={self.date}, rth={self.rth})"

    @classmethod
    def from_redis(cls, data: dict):
        return cls(
            date=data["dt"],
            symbol=data["symbol"],
            open=data["o"],
            high=data["h"],
            low=data["l"],
            close=data["c"],
            volume=data["vol"],
        )
