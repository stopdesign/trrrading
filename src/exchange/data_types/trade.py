from dataclasses import dataclass


@dataclass
class Trade:
    price: float
    volume: int
