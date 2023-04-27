import logging
from collections import namedtuple

from trader.data_types import Order
from trader.exchange import BaseExchange, Consolidator, Data
from trader.indicator.base import BaseIndicator

log = logging.getLogger("strategy")


class BaseStrategy:
    exchange: BaseExchange

    def __init__(self, **kwargs):
        self.exchange = kwargs.pop("exchange")
        self.name = str(kwargs.pop("strategy", None))
        self.sid: str = str(kwargs.get("sid"))
        self.params = namedtuple(self.name, kwargs.keys())(*kwargs.values())
        self.data = []
        self.warmed = False
        self.log = logging.getLogger(self.name.lower())

        self.bars = self.exchange.bars
        self.quotes = self.exchange.quotes
        self.positions = self.exchange.positions
        self.account = self.exchange.account
        self.orders = self.exchange.orders

        self.update_order = self.exchange.update_order

        self.on_start()

        self.log_strategy_info()

    def __repr__(self):
        return str(self.params)

    def log_strategy_info(self):
        log.info(self)

        for data_source in self.data_sources:
            log.info(data_source)

        for consolidator in self.consolidators:
            log.info(consolidator)

        for indicator in self.indicators:
            log.info(indicator)

    def place_order(self, order: Order):
        order.strategy = self
        self.exchange.place_order(order)

    def update_order(self, *args, **kwargs):
        self.exchange.update_order(*args, **kwargs)

    def cancel_order(self, *args, **kwargs):
        self.exchange.cancel_order(*args, **kwargs)

    @property
    def market_system(self):
        return f"{self.sid}-{self.name}"

    @property
    def indicators(self):
        for attr in vars(self).values():
            if isinstance(attr, BaseIndicator):
                yield attr

    @property
    def data_sources(self):
        for attr in vars(self).values():
            if isinstance(attr, Data):
                if not isinstance(attr, Consolidator):
                    yield attr

    @property
    def consolidators(self):
        for attr in vars(self).values():
            if isinstance(attr, Consolidator):
                yield attr

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
