from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class BidAsk:
    date: datetime
    symbol: str
    bid: Decimal = Decimal("nan")
    ask: Decimal = Decimal("nan")
    rth: bool = None

    @classmethod
    def from_redis_quote(cls, data: dict):
        return cls(
            date=data["dt"],
            symbol=data["symbol"],
            bid=Decimal(data["av_bid"]),
            ask=Decimal(data["av_ask"]),
        )

    @classmethod
    def from_redis_trade(cls, data: dict):
        return cls(
            date=data["dt"],
            symbol=data["symbol"],
            bid=Decimal(data["l"]),
            ask=Decimal(data["h"]),
        )
