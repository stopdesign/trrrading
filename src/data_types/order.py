from dataclasses import dataclass

@dataclass(slots=True)
class Order:
    type: str
    amount: int
    status: str
    fill_price: float = None
    stop_price: float = None
    limit_price: float = None
