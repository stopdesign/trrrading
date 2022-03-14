import logging
from decimal import Decimal
from exchange import BaseExchange
from exchange.mixin import Healthcheck
from termcolor import colored

from main.models import Order, Instrument

log = logging.getLogger("broker")


class IBWebExchange(BaseExchange, Healthcheck):
    healthcheck_interval = 60
    price_precision = Decimal("0.01")

    def __init__(self, instruments: dict, **kwargs):
        super().__init__(instruments, **kwargs)
        self.cash_initial = kwargs.get("cash", Decimal("10000"))
        self.cash = self.cash_initial
        self.latest_order_id = None
        self.backtest = kwargs["backtest"]

    def get_positions(self):

        # взять начальную позицию, применить все изменения позиции с того момента

        if self.backtest:
            return self.positions

        # FIXME: убрать хардкодинг аккаунта
        account_id = 1

        real_positions = {}

        for symbol, position in self.positions.items():
            stock_symbol, exchange_symbol = symbol.split(".")
            instrument = Instrument.objects.get(symbol=stock_symbol)
            orders_after_start = Order.objects.filter(
                account_id=account_id,
                id__gt=self.latest_order_id,
                instrument=instrument,
            )
            real_positions[symbol] = dict(self.positions[symbol])
            for order in orders_after_start:
                if order.action == Order.Side.buy:
                    real_positions[symbol]["amount"] += order.filled
                if order.action == Order.Side.sell:
                    real_positions[symbol]["amount"] -= order.filled

        return real_positions

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            if position["amount"]:
                if price := self.get_price(symbol, "mid"):
                    mid = Decimal(price)
                    total_value += position["amount"] * (mid - position["price"])
                else:
                    log.warning(colored(f"No price for {symbol}", "red"))
        return total_value
