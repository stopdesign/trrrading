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
        self.data_1m = Data(self.sid, rth=1, on_bar=self.on_bar)

        # Подписка на другой таймфрейм
        # self.ind_tf = Consolidator(self.data_1m, "2m")

        self.dc = DonchianChannels(self.data_1m, self.length)
        # self.ma = MovingAverage(self.data_1m, interval=200)

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

        channel = self.dc.value

        log.info(f"channel: {channel}")
        # print(colored(channel, "blue"), bar)

        self.set_or_change_stops()

    def set_or_change_stops(self):
        active = ["New", "Sent", "PreSubmitted", "Submitted"]
        in_tws = ["New", "Sent", "PreSubmitted"]  # у Submitted нельзя менять цену

        # как-то получить актуальный ордер
        # что делать, если есть два ордера?
        orders = []
        for order in self.exchange.orders:
            if order.status in active and order.sid == self.sid:
                orders.append(order)

        channel = self.dc.value

        if not (channel["lb"] and channel["ub"]):
            log.error(f"Indicator wasn't warmed up? {self.sid} {channel}")
            return

        # FIXME: сделать удобный способ добывать позиции, без get
        # как-то получить позицию по данному инструменту
        def_pos = Position(self.sid, capital=Decimal(100000), amount=Decimal(0))
        position = self.exchange.positions.get(self.sid, def_pos)

        ub = round(channel["ub"] / 0.25) * 0.25
        lb = round(channel["lb"] / 0.25) * 0.25

        money = 10000

        for order in orders:
            if order.status in in_tws:
                if order.amount > 0:
                    target_amount = +int(money / ub)
                    self.update_order(order, stop_price=ub, amount=target_amount)
                if order.amount < 0:
                    target_amount = -int(money / lb)
                    self.update_order(order, stop_price=lb, amount=target_amount)

        if not orders:

            if position.amount >= 0:
                current_amount = position.amount
                target_amount = -int(money / lb)
                self.stop_order(target_amount - current_amount, lb)

            if position.amount <= 0:
                current_amount = position.amount
                target_amount = +int(money / ub)
                self.stop_order(target_amount - current_amount, ub)


    def on_order_event(self, payload):
        pass
        # log.info(f"On order event: {payload}")
