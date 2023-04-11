import logging
from decimal import Decimal
from typing import Callable

from trader.data_types import Order, Position

from .base_exchange import BaseExchange
from .matcher import LocalMatcher

log = logging.getLogger("emulator")


class EmulatorPositions(dict):
    """
    В эмуляторе есть нулевая позиция для любого символа.
    """

    def __init__(self, capital: Decimal | int):
        self.capital = Decimal(capital)

    def __missing__(self, key):
        self[key] = Position(key, self.capital, Decimal(0))
        return self[key]

    def get(self, key, default=None):
        return self[key]


class Emulator(BaseExchange):
    """
    Эмуляция торговли.
    """

    def __init__(self, on_event: Callable):
        super().__init__(on_event)

        self.trades = []

        # TODO: настройки бы пробросить...
        self.matcher = LocalMatcher(self)

        # начальное состояние аккаунта при эмуляции
        self.account["net_value"] = 100_000

        # обнулить позиции по всем символам
        self.positions = EmulatorPositions(100_000)

    def place_order(self, order: Order):
        """
        Создание ордера из стратегии.
        """
        # log.info(colored(f"PLACE {order}"))
        self.orders.append(order)
        self.matcher.process_order(order)

    def update_order(self, order: Order, **kwargs):
        """
        Редактирование ордера из стратегии.
        """
        updated = False
        for key, value in kwargs.items():
            if getattr(order, key, None) != value:
                updated = True
            setattr(order, key, value)

    def cancel_order(self, order: Order):
        raise NotImplementedError

    def process_orders(self):
        """
        Посмотреть список ордеров и изобразить их исполнение по известным ценам.
        """
        for order in [o for o in self.orders if o.status == "New"]:
            self.matcher.process_order(order)
