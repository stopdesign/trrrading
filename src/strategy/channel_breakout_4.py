import logging
from decimal import Decimal

from data_types import Bar, Order, Trade
from indicator.donchian_channels import DonchianChannels
from strategy import BaseStrategy

log = logging.getLogger("strategy")


class ChBrStop(BaseStrategy):
    """
    Стратегия ChBr на Stop-ордерах
    """

    def on_start(self):

        self.symbol = "URA.ARCA"  # можно брать из конфига

        # TODO: можно перейти на такой формат подписки.
        # Тогда это можно передать в индикатор как источник данных.
        # self.ura = DataSource("URA", "5m", rth=True, on_bar=self.on_bar)

        self.dc = DonchianChannels(self.length)

    def market_order(self, amount):
        order = Order(type="market", amount=amount, status="new")
        self.exchange.place_order(order)

    def stop_order(self, amount, price):
        order = Order(type="stop", amount=amount, status="new", stop_price=price)
        self.exchange.place_order(order)

    def on_bar(self, bar: Bar):

        if not self.warmed:
            return

        # как-то получить актуальный ордер
        # что делать, если есть два ордера?
        orders = []
        for order in self.exchange.orders:
            if order.status == "new":
                orders.append(order)

        channel = self.dc.value

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
