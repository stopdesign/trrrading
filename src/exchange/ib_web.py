import logging
from decimal import Decimal
from termcolor import cprint, colored
from exchange import BaseExchange
from exchange.mixin import Healthcheck

log = logging.getLogger("broker")


class IBWebExchange(BaseExchange, Healthcheck):
    healthcheck_interval = 60
    rel_price_cap = 0.005  # на столько limit price будет хуже mid_price
    price_precision = Decimal("0.01")

    backtest = True

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)
        self.cash_initial = kwargs.get("cash", Decimal("100000"))
        self.cash = self.cash_initial

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            mid = Decimal(str(self.get_price(symbol, "mid")))
            total_value += position["amount"] * (mid - position["price"])
        return total_value
