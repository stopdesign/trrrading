from collections import namedtuple
from trader.indicator.base import BaseIndicator
from trader.exchange import BaseExchange


class BaseStrategy:

    exchange: BaseExchange

    def __init__(self, **kwargs):
        self.exchange = kwargs.pop("exchange")
        self.name = kwargs.pop("strategy", None)
        self.symbol = kwargs.get("symbol")
        self.length = kwargs.get("length")
        self.params = namedtuple(self.name, kwargs.keys())(*kwargs.values())
        self.data = []
        self.warmed = False

        self.bars = self.exchange.bars
        self.quotes = self.exchange.quotes
        self.positions = self.exchange.positions
        self.account = self.exchange.account
        self.orders = self.exchange.orders

        self.place_order = self.exchange.place_order
        self.update_order = self.exchange.update_order

        self.on_start()

    def __repr__(self):
        return str(self.params)

    @property
    def market_system(self):
        return f"{self.symbol}_{self.name}"

    @property
    def indicators(self):
        return filter(lambda a: isinstance(a, BaseIndicator), self.__dict__.values())

    def on_start(self):
        pass

    @property
    def info(self):
        return f"{self}, data_len={len(self.data)}"

    def on_bar(self, data):
        pass

    def on_quote(self, data):
        pass

    def on_tick(self, data):
        pass
