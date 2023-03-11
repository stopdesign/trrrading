from dataclasses import dataclass
from secrets import token_hex
from decimal import Decimal


@dataclass(slots=True)
class Order:
    instrument: str
    type: str
    amount: int
    status: str
    local_id: str|None = None
    limit_price: float = float("nan")
    stop_price: float = float("nan")
    fill_price: Decimal = Decimal("nan")

    @staticmethod
    def new_local_id():
        return "bot_" + token_hex(4)

    def __post_init__(self):
        if not self.local_id:
            self.local_id = Order.new_local_id()
