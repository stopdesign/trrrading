from decimal import Decimal
import logging
from datetime import datetime, timedelta, timezone

from trader.data_types import Bar, Order, Trade, Position
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels, MovingAverage

from .base import BaseStrategy

log = logging.getLogger("strategy")


class ChBrStop(BaseStrategy):
    """
    Стратегия ChBr на Stop-ордерах
    """

    def on_start(self):
        # Подписка на данные
        self.data_1m = Data(self.sid, rth=True, on_bar=self.on_bar)

        self.dc = DonchianChannels(
            self.data_1m,
            skip_extra_hours=True,
            skip_zero_volume=True,
            length=self.length,
        )

        # Подписка на другой таймфрейм
        # self.ind_tf = Consolidator(self.data_1m, "2m")
        # self.ma = MovingAverage(self.data_1m, interval=200)

    def get_amount(self, price):
        return int(100_000 / price)

    def stop_order(self, amount, price):
        order = Order(self.sid, type="stop", amount=amount, stop_price=price)
        # log.error(f"Place STOP ORDER {order}")
        self.place_order(order)

    def on_tick(self, trade: Trade):
        pass

    def on_bar(self, bar: Bar):

        if not self.warmed:
            return

        # Это нужно только при живой торговле

        # Если stopLimit-order долго висит в состоянии Submitted в TWS,
        # значит limit был слишком близко, и ордер не успел сработать.
        in_tws = ["Submitted"]  # stop-order в состоянии triggered, например
        too_old = datetime.now(timezone.utc) - timedelta(minutes=5)

        for o in self.exchange.orders:
            # cprint(f"{o} {o.status}", "magenta")
            if o.status in in_tws and o.created_at and o.created_at < too_old:
                self.exchange.cancel_order(o)

        # channel = self.dc.value
        # log.info(f"channel: {channel}")
        # print(colored(channel, "blue"), bar)

        self.set_or_change_stops()

    def set_or_change_stops(self):
        active = ["New", "Sent", "PreSubmitted", "Submitted"]
        in_tws = ["New", "Sent", "PreSubmitted"]  # у Submitted нельзя менять цену

        # как-то получить актуальный ордер
        # что делать, если есть два ордера?

        # FIXME: сделать нормально
        orders = []
        for order in self.exchange.orders:
            if order.status in active and order.sid == self.sid:
                orders.append(order)

        channel = self.dc.value

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.sid} {channel}")
            return

        position = self.exchange.positions[self.sid]

        # FIXME: вынести куда-то?
        ub = channel["ub"] #/ 0.01) * 0.01
        lb = channel["lb"] # / 0.01) * 0.01

        for order in orders:
            if order.status in in_tws:
                if order.amount > 0:
                    target_amount = +self.get_amount(ub)
                    # print(">>> update", ub)
                    self.update_order(order, stop_price=ub, amount=target_amount)
                if order.amount < 0:
                    target_amount = -self.get_amount(lb)
                    self.update_order(order, stop_price=lb, amount=target_amount)

        if not orders:

            if position.amount >= 0:
                current_amount = position.amount
                target_amount = -self.get_amount(lb)
                self.stop_order(target_amount - current_amount, lb)

            if position.amount <= 0:
                current_amount = position.amount
                target_amount = +self.get_amount(ub)
                self.stop_order(target_amount - current_amount, ub)

