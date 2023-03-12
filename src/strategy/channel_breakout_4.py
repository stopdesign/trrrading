import logging
from decimal import Decimal

from data_types import Bar, Order, Trade
from indicator import DonchianChannels, MovingAverage
from strategy import BaseStrategy

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
        self.exchange.place_order(order)

    def on_bar(self, bar: Bar):

        if not self.warmed:
            return

        # как-то получить актуальный ордер
        # что делать, если есть два ордера?
        orders = []
        for order in self.exchange.orders:
            if order.status == "New":  # FIXME в TWS они будут не New
                orders.append(order)

        channel = self.dc.value

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.instrument} {channel}")
            return

        # log.info(f"channel: {channel}")

        # как-то получить позицию по данному инструменту
        position = self.exchange.positions[self.symbol]

        for order in orders:
            if order.amount > 0:
                order.stop_price=channel["ub"]
            if order.amount < 0:
                order.stop_price=channel["lb"]

        if not orders:

            if position.amount >= 0:
                current_amount = position.amount
                target_amount = -int(100_000 / channel["lb"])
                self.stop_order(target_amount - current_amount, channel["lb"])

            if position.amount <= 0:
                current_amount = position.amount
                target_amount = +int(100_000 / channel["ub"])
                self.stop_order(target_amount - current_amount, channel["ub"])

    def on_trade(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        # print("strategy on trade", self.dc.value)

        if not self.warmed:
            return

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
