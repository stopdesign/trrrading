from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class Bar:
    date: datetime
    sid: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = None
    rth: bool = None

    def __repr__(self):
        return f"Bar({self.sid}, date={self.date}, rth={self.rth}, v={self.volume})"

    @classmethod
    def from_redis(cls, data: dict):
        return cls(
            date=data["dt"],
            sid=data["sid"],
            open=data["o"],
            high=data["h"],
            low=data["l"],
            close=data["c"],
            volume=data.get("v") or data.get("vol") or 0,
            rth=data["rth"],
        )
