from dataclasses import dataclass
from datetime import datetime
from typing import Union


@dataclass
class Bar:
    date: Union[None, datetime]
    open: float
    high: float
    low: float
    close: float
    volume: int
    rth: bool
    ticker: str
