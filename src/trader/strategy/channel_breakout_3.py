import logging

from trader.data_types import Bar, Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels, MovingAverage

from .base import BaseStrategy

log = logging.getLogger("strategy")


class ChBr(BaseStrategy):
    def on_start(self):
        # Подписка на данные
        self.data_1m = Data(self.sid, rth=True, on_bar=self.on_bar)

        self.ind_tf = Consolidator(self.data_1m, "15m")
        self.ma = MovingAverage(self.data_1m, length=200)

        self.dc = DonchianChannels(
            self.data_1m,
            skip_extra_hours=True,
            skip_zero_volume=True,
            length=self.length or 0,
        )

    def get_amount(self, price):
        return 1
        # return int(1_000 / price)

    def market_order(self, amount):
        order = Order(
            self.sid,
            type="MKT",
            amount=amount,
            ib_algo={"strategy": "Adaptive", "params": {"adaptivePriority": "Normal"}},
        )
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

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.sid} {channel}")
            return

        if not bar.rth:  # trade.rth пока нет
            return

        for order in self.orders:
            active = ["New", "Sent", "PreSubmitted", "Submitted"]
            if order.sid == self.sid and order.status in active:
                log.warn(f"strategy has live order, {order}")
                return

        position = self.positions[self.sid]

        # print(
        #     f"Position: {position.amount}, "
        #     f"Trade time: {trade.date.time()}, price: {trade.price:0.2f}, "
        #     f"Channel: {channel} "
        # )

        current_amount = position.amount
        target_amount = current_amount

        if current_amount <= 0 and trade.price > channel["ub"]:
            target_amount = +self.get_amount(trade.price)

        if current_amount >= 0 and trade.price < channel["lb"]:
            target_amount = -self.get_amount(trade.price)

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
