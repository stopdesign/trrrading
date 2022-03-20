from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Union


@dataclass
class BidAsk:
    date: Union[None, datetime]
    bid: Decimal = Decimal("nan")
    ask: Decimal = Decimal("nan")
