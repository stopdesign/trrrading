import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from termcolor import colored

from trader.data_types import Bar, Order, Trade
from trader.indicator import DonchianChannels, MovingAverage
from trader.strategy import BaseStrategy

log = logging.getLogger("strategy")


class ChBrStop(BaseStrategy):
    """
    Стратегия ChBr на Stop-ордерах
    """

    def on_start(self):
        self.instrument = str(self.symbol)

        # TODO: можно перейти на такой формат подписки.
        # Тогда это можно передать в индикатор как источник данных.
        # self.ura = DataSource("URA", "5m", rth=True, on_bar=self.on_bar)

        self.dc = DonchianChannels(self.length)

        self.ma = MovingAverage(self.length)

    def market_order(self, amount):
        order = Order(self.instrument, type="market", amount=amount)
        self.place_order(order)

    def stop_order(self, amount, price):
        order = Order(self.instrument, type="stop", amount=amount, stop_price=price)
        self.place_order(order)

    def on_bar(self, bar: Bar):
        if not self.warmed:
            return

        channel = self.dc.value

        # log.info(f"channel: {channel}")
        print(colored(channel, "blue"), bar)

        self.set_or_change_stops()

    def set_or_change_stops(self):
        active = ["New", "Sent", "PreSubmitted", "Submitted"]
        in_tws = ["PreSubmitted", "Submitted"]

        # как-то получить актуальный ордер
        # что делать, если есть два ордера?
        orders = []
        for order in self.exchange.orders:
            if order.status in active and order.instrument == self.instrument:
                orders.append(order)

        channel = self.dc.value

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.instrument} {channel}")
            return

        # как-то получить позицию по данному инструменту
        position = self.exchange.positions[self.symbol]

        for order in orders:
            if order.status in in_tws:
                if order.amount > 0:
                    self.update_order(order, stop_price=channel["ub"])
                if order.amount < 0:
                    self.update_order(order, stop_price=channel["lb"])

        if not orders:
            if position.amount >= 0:
                current_amount = position.amount
                target_amount = -int(10_000 / channel["lb"])
                self.stop_order(target_amount - current_amount, channel["lb"])

            if position.amount <= 0:
                current_amount = position.amount
                target_amount = +int(10_000 / channel["ub"])
                self.stop_order(target_amount - current_amount, channel["ub"])

    def on_trade(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        # print("strategy on trade", self.dc.value)

        if not self.warmed:
            return

    def on_order_event(self, payload):
        in_tws = ["PreSubmitted", "Submitted"]
        too_old = datetime.now(timezone.utc) - timedelta(minutes=10)

        # TODO: отменять только тот ордер, цена которого лучше рынка
        for o in self.exchange.orders:
            if o.status in in_tws:
                # print(">>>>", o.local_id, o.created_at, too_old)
                if o.created_at and o.created_at < too_old:
                    self.exchange.cancel_order(o)
