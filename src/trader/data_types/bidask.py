from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


QUANTIZE_EXP = Decimal("1.00")

@dataclass(slots=True)
class BidAsk:
    date: datetime
    sid: str
    bid: Decimal = Decimal("nan")
    ask: Decimal = Decimal("nan")
    rth: bool = None

    def __repr__(self):
        return (
            "BidAsk({0.sid}, {0.date}, bid={0.bid}, ask={0.ask}, rth={0.rth})"
        ).format(self)

    @classmethod
    def from_redis_quote(cls, data: dict):
        return cls(
            date=data["dt"],
            sid=data["sid"],
            # FIXME: плохо хардкодить количество знаков, но str тоже плохо
            bid=Decimal(data["av_bid"]).quantize(QUANTIZE_EXP),
            ask=Decimal(data["av_ask"]).quantize(QUANTIZE_EXP),
        )

    @classmethod
    def from_redis_trade(cls, data: dict):
        return cls(
            date=data["dt"],
            sid=data["sid"],
            bid=Decimal(data["l"]).quantize(QUANTIZE_EXP),
            ask=Decimal(data["h"]).quantize(QUANTIZE_EXP),
        )
