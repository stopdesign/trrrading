from collections import defaultdict
from decimal import Decimal
from typing import Optional


class BaseExchange:
    """
    Биржа
    """

    def __init__(self, symbols: list, **kwargs):
        self.symbols = symbols
        self.quotes = {}
        self.positions = {}
        self.cash = Decimal(0)

    def get_price(self, symbol: str, side: str) -> Optional[Decimal]:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"][0]["price"]
            if side == "buy":
                return quotes["ask"][0]["price"]

    def create_order(self, side: str, size: int, symbol: str):
        raise NotImplementedError()

    def start_listen(self, on_event, loop=None):
        pass

    def stop_listen(self, loop=None):
        pass

    def print_final_info(self):
        pass

    def load_last_orders(self):
        return []

    def get_positions(self):
        pass

    def get_cash_value(self):
        pass
