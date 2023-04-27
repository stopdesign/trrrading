from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Trade:
    date: datetime
    sid: str
    price: Decimal
    volume: int | None = None
    rth: bool | None = None

    def __repr__(self):
        return (
            "Trade({0.sid}, {0.date}, "
            "price={0.price:0.2f}, volume={0.volume}, rth={0.rth})"
        ).format(self)
