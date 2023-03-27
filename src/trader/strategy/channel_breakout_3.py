import logging
from decimal import Decimal

from termcolor import colored

from trader.data_types import Bar, Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels

from .base import BaseStrategy

log = logging.getLogger("strategy")


class ChBr(BaseStrategy):
    def on_start(self):
        # Подписка на данные
        self.data_1m = Data(self.sid, rth=1, on_bar=self.on_bar)

        self.dc = DonchianChannels(self.data_1m, self.length)

    def market_order(self, amount):
        order = Order(self.sid, type="market", amount=amount)
        self.place_order(order)

    def on_bar(self, bar: Bar):
        pass

    def on_tick(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        if not self.warmed:
            return

        bars = self.bars[self.sid]
        bar = bars[-1] if bars else None
        channel = self.dc.value

        if not bar:
            return

        # print(colored(channel, "blue"), bar, colored(trade, "green"))

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.sid} {channel}")
            return

        if not bar.rth:  # trade.rth пока нет
            return

        for order in self.orders:
            # TODO: проверить, что инструмент совпадает
            active = ["New", "Sent", "PreSubmitted", "Submitted"]
            if order.sid == self.sid and order.status in active:
                log.warn(f"strategy has live order, {order}")
                return

        position = self.positions[self.sid]

        # log.info(
        #     f"strategy on trade, {channel}, {trade}, "
        #     f"sid: {position.sid}, "
        #     f"amount: {position.amount}"
        # )

        current_amount = position.amount
        target_amount = current_amount

        if current_amount <= 0 and trade.price > channel["ub"]:
            target_amount = +int(10_000 / trade.price)
            # target_amount = +2

        if current_amount >= 0 and trade.price < channel["lb"]:
            target_amount = -int(10_000 / trade.price)
            # target_amount = -2

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
