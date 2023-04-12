import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from secrets import token_hex


@dataclass(slots=True)
class Order:
    sid: str
    type: str
    amount: int
    status: str = "New"
    local_id: str | None = None
    limit_price: float = float("nan")
    stop_price: float = float("nan")
    fill_price: Decimal = Decimal("nan")
    created_at: datetime | None = None
    strategy: None = None
    rth: bool = True

    @staticmethod
    def new_local_id():
        return "bot_" + token_hex(4)

    def __post_init__(self):
        if not self.local_id:
            self.local_id = Order.new_local_id()

    def __repr__(self):
        txt = f"{self.local_id}, {self.sid}, {self.type}, {self.amount:+0.2f}, "

        if self.type == "limit":
            txt += f"limit={self.limit_price:0.2f}, "

        elif self.type == "stop":
            txt += f"stop={self.stop_price:0.2f}, "

        if self.fill_price and not math.isnan(self.fill_price):
            txt += f"fill={self.fill_price:0.2f}, "

        txt = txt.strip().strip(",")
        return f"Order({txt})"
