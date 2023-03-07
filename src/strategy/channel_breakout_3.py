import logging
from decimal import Decimal

from data_types import Bar, Order, Trade
from indicator.donchian_channels import DonchianChannels
from strategy import BaseStrategy

log = logging.getLogger("strategy")


class ChBr(BaseStrategy):

    def on_start(self):

        self.symbol = "URA.ARCA"  # можно брать из конфига

        # TODO можно перейти на такой формат подписки.
        # Тогда это можно передать в индикатор как источник данных.
        # self.ura = DataSource("URA", "5m", rth=True, on_bar=self.on_bar)

        self.dc = DonchianChannels(self.length)

    def market_order(self, amount):
        order = Order(type="market", amount=amount, status="new")
        self.exchange.place_order(order)

    def on_bar(self, bar: Bar):
        pass

    def on_trade(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        # print("strategy on trade", self.dc.value)

        if not self.warmed:
            return

        bars = self.exchange.bars["URA.ARCA"]
        bar = bars[-1] if bars else None
        channel = self.dc.value

        if not bar or not channel["lb"]:
            return

        if not (trade.rth and bar.rth):
            return

        for order in self.exchange.orders:
            if order.status == "new":
                return

        position = self.exchange.positions.get(self.symbol)

        current_amount = position.amount
        target_amount = current_amount

        if current_amount <= 0 and trade.price > channel["ub"]:
            target_amount = +Decimal(100_000 / trade.price)

        if current_amount >= 0 and trade.price < channel["lb"]:
            target_amount = -Decimal(100_000 / trade.price)

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
