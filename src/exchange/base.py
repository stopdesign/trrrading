from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from termcolor import cprint
from util import parse_quote


class BaseExchange:
    """
    Биржа
    """

    # FIXME: заменить price на None
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

    def add_quote(self, dt, symbol, event):
        current_quote = self.quotes.get(symbol)
        if current_quote and current_quote["dt"] > dt:
            return
        self.quotes[symbol] = {
            "ask": list(map(parse_quote, event["ask"])),
            "bid": list(map(parse_quote, event["bid"])),
            "dt": dt,
        }

    def fetch_backtest_data(self, symbol, start_at, minutes):
        pass

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
                if price is None:
                    # FIXME:
                    cprint(f"WARNING: {symbol} price is {price}", "yellow")
                    continue
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
            if position["amount"] < 0:
                price = self.get_price(symbol, "buy")
                if price is None:
                    cprint(f"WARNING: {symbol} price is {price}", "yellow")
                    continue
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
        return total_value
