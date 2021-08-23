from dataclasses import dataclass


@dataclass
class Fee:
    fixed_rate: float = 0.0
    fixed_price: float = 0.0

    def for_amount(self, amount: float) -> float:
        return amount * self.fixed_rate + self.fixed_price
