import logging
from decimal import Decimal

from data_types import Bar, Order, Trade
from indicator.donchian_channels import DonchianChannels
from strategy import BaseStrategy

log = logging.getLogger("strategy")


class ChBr(BaseStrategy):

    def on_start(self):

        # self.symbol = "MES.CME"  # можно брать из конфига
        self.instrument = "MESH3.CME"

        # TODO можно перейти на такой формат подписки.
        # Тогда это можно передать в индикатор как источник данных.
        # self.ura = DataSource("URA", "5m", rth=True, on_bar=self.on_bar)

        self.dc = DonchianChannels(self.length)

    def market_order(self, amount):
        order = Order(
            instrument=self.instrument,
            type="market",
            amount=amount,
            status="New",
        )
        self.place_order(order)

    def on_bar(self, bar: Bar):
        pass

    def on_trade(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        if not self.warmed:
            return

        bars = self.bars[self.instrument]
        bar = bars[-1] if bars else None
        channel = self.dc.value

        if not bar:
            return

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.instrument} {channel}")
            return

        if not (trade.rth and bar.rth):
            return

        for order in self.orders:
            # TODO: проверить, что инструмент совпадает
            if order.status in ["New", "PreSubmitted", "Submitted"]:
                log.warn(f"strategy has live order, {order}")
                return

        position = self.positions[self.instrument]

        # log.info(
        #     f"strategy on trade, {channel}, {trade}, "
        #     f"symbol: {position.symbol}, "
        #     f"amount: {position.amount}"
        # )

        current_amount = position.amount
        target_amount = current_amount

        if current_amount <= 0 and trade.price > channel["ub"]:
            target_amount = +Decimal(100_000 / trade.price)
            # target_amount = +2

        if current_amount >= 0 and trade.price < channel["lb"]:
            target_amount = -Decimal(100_000 / trade.price)
            # target_amount = -2

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
