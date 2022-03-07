from dataclasses import dataclass
from datetime import datetime
from typing import Union


@dataclass
class Trade:
    date: Union[None, datetime]
    price: float
    volume: int
