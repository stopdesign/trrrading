from decimal import Decimal
from typing import Optional


class BaseExchange:
    """
    Биржа
    """

    empty_position = {"amount": Decimal("0"), "price": Decimal("0")}

    def __init__(self, symbols: list, **kwargs):
        self.symbols = symbols
        self.quotes = {}
        self.positions = {}
        self.cash = Decimal(0)
        self.fee_rate = Decimal(0)

    def get_price(self, symbol: str, side: str) -> Optional[Decimal]:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"][0]["price"]
            if side == "buy":
                return quotes["ask"][0]["price"]

    def trade(self, side: str, amount: int, symbol: str):
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

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                price = self.get_price(symbol, "sell")
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
            if position["amount"] < 0:
                price = self.get_price(symbol, "buy")
                total_value += position["amount"] * (position["price"] - price)
                total_value -= self.fee_rate * position["amount"]
        return total_value
