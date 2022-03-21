from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Trade:
    date: datetime
    symbol: str
    price: Decimal
    volume: int = None
    rth: bool = None
