import logging
from collections import defaultdict
from copy import copy
from decimal import Decimal
from typing import Callable

from data_types import Bar, BidAsk

log = logging.getLogger("base_exchange")


class BaseExchange:
    """
    Хранит локальную версию состояния биржи.
    Хранит состояние индикаторов и торговые данные.
    При живой торговле занимается обновлением состояния и пробросом ордера.
    При эмуляции сам занимается исполнением ордера (через matcher).
    """

    def __init__(self, on_event: Callable):
        self.positions = {}
        self.orders = []
        self.account = {}
        self.quotes = {}  # последнее значение bid-ask
        self.bars = defaultdict(list)  # market data bar including indicators values
        self.dt_last = None
        self.on_event = on_event

    # NOTE: код из старого класса Exchange
    def get_price(self, symbol: str, side: str) -> Decimal:
        if quotes := self.quotes.get(symbol):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]
            if side == "mid":
                return (quotes["ask"] + quotes["bid"]) / 2
        return Decimal("nan")

    # NOTE: код из старого класса Exchange
    def add_quote(self, dt, symbol, payload):
        """
        Сохранить BID и ASK как актуальное состояние стакана на бирже.
        """
        current_quote = self.quotes.get(symbol)
        if current_quote and current_quote["dt"] > dt:
            return
        if symbol not in self.quotes:
            self.quotes[symbol] = {}
        # ask и bid могут приходить независимо
        if payload.ask:
            self.quotes[symbol]["ask"] = Decimal(payload.ask)
            self.quotes[symbol]["dt"] = dt
        if payload.bid:
            self.quotes[symbol]["bid"] = Decimal(payload.bid)
            self.quotes[symbol]["dt"] = dt
        self.dt_last = dt

    def on_quote(self, dt, bid_ask: BidAsk):
        self.add_quote(dt, bid_ask.symbol, bid_ask)

    def on_bar(self, dt, bar: Bar):
        self.dt_last = dt
        self.bars[bar.symbol].append(copy(bar))

    def process_orders(self):
        """
        Только для эмуляции.
        """
        raise NotImplementedError

    def on_broker_update(self, payload):
        """
        Только для живой торговли
        """
        raise NotImplementedError
