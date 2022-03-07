from dataclasses import dataclass
from datetime import datetime
from typing import Union


@dataclass
class BidAsk:
    date: Union[None, datetime]
    bid: float
    ask: float
