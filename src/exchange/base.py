from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from strategy import Signal


class BaseExchange:
    """
    Биржа
    """

    on_trade: Callable
    on_quote: Callable
    on_interval: Callable
    position: Optional[str]
    position_size: int
    position_open_price: Optional[Decimal]
    cash: Decimal

    def __init__(
        self, on_trade: Callable, on_quote: Callable, on_interval: Callable, **params
    ):
        self.on_trade = on_trade
        self.on_quote = on_quote
        self.on_interval = on_interval
        # TODO: получить баланс
        # TODO: получить список открытых позиций и висящих ордеров
        self.position = None
        self.position_size = 0
        self.position_open_price = None
        self.cash = Decimal(0)

    def create_order(self, side: str, size: int):
        raise NotImplementedError()

    def open_position(self, dt: datetime, signal: Signal, size: int):
        raise NotImplementedError()

    def close_position(self, dt: datetime):
        raise NotImplementedError()

    def start_listen(self, loop=None):
        pass

    def stop_listen(self, loop=None):
        pass

    def print_final_info(self):
        pass
