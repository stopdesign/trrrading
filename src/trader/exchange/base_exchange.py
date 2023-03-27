import logging
from collections import defaultdict
from copy import copy
from decimal import ROUND_DOWN, Decimal
from typing import Callable

from trader.data_types import Bar, BidAsk, Order

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
    def get_price(self, sid: str, side: str) -> Decimal:
        if quotes := self.quotes.get(sid):
            if side == "sell":
                return quotes["bid"]
            if side == "buy":
                return quotes["ask"]
            if side == "mid":
                return (quotes["ask"] + quotes["bid"]) / 2
        return Decimal("nan")

    # NOTE: код из старого класса Exchange
    def add_quote(self, dt, sid: str, payload):
        """
        Сохранить BID и ASK как актуальное состояние стакана на бирже.
        """
        current_quote = self.quotes.get(sid)
        if current_quote and current_quote["dt"] > dt:
            return
        if sid not in self.quotes:
            self.quotes[sid] = {}
        # ask и bid могут приходить независимо
        if payload.ask:
            self.quotes[sid]["ask"] = Decimal(payload.ask)
            self.quotes[sid]["dt"] = dt
        if payload.bid:
            self.quotes[sid]["bid"] = Decimal(payload.bid)
            self.quotes[sid]["dt"] = dt
        self.dt_last = dt

    def on_quote(self, dt, bid_ask: BidAsk):
        self.add_quote(dt, bid_ask.sid, bid_ask)

    def on_bar(self, dt, bar: Bar):
        self.dt_last = dt
        self.bars[bar.sid].append(copy(bar))

    def get_net_value(self) -> Decimal:
        net = Decimal(self.account.get("net_value", "NaN"))
        # net = Decimal(0)
        # for strategy in self.strategies:
        #     position = self.__positions[strategy.market_system]
        #     if position.amount and not math.isnan(position.amount):
        #         side = "sell" if position.amount > 0 else "buy"
        #         price = self.exchange.get_price(strategy.sid, side)
        #         net += position.amount * (price - position.avg_price)
        #     net += position.profit
        return net.quantize(Decimal("0.01"), ROUND_DOWN)

    def place_order(self, order: Order):
        raise NotImplementedError

    def update_order(self, order: Order, **kwargs):
        raise NotImplementedError

    def cancel_order(self, order: Order):
        raise NotImplementedError

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
