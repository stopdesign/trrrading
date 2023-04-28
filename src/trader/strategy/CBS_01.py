from datetime import datetime, timedelta, timezone

from trader.data_types import Bar, Order
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels, MovingAverage
from trader.strategy import BaseStrategy


class CBS_01(BaseStrategy):
    """
    Стратегия Channel Breakout на Stop-ордерах.
    """

    def on_start(self):
        # Параметры стратегии
        length = self.params.length
        length_ma = self.params.length_ma

        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=True, on_bar=self.on_bar)

        # Консолидатор данных в более крупный таймфрейм
        self.ind_tf = Consolidator(self.data_1m, "15m")

        # Инициализация индикаторов
        self.ma = MovingAverage(self.data_1m, length=length_ma)
        self.dc = DonchianChannels(self.data_1m, length=length)

    def get_amount(self, price):
        # Подсчет размера позиции
        return 1
        # return int(100_000 / price)

    def stop_order(self, amount, price):
        order = Order(self.sid, "STP", amount, stop_price=price, rth=False)
        self.place_order(order)

    def on_bar(self, bar: Bar):
        # Отменить подвисшие triggered-ордеры
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        for o in self.orders.filter(self.sid, status=["Submitted"], before=old):
            self.cancel_order(o)

        self.manage_orders()

    def manage_orders(self):
        if not (self.warmed and self.dc.ready):
            return

        # Активные ордеры нужного инструмента
        orders = self.orders.filter(self.sid).active()

        ub, lb = self.dc.value["ub"], self.dc.value["lb"]

        current_amount = self.positions[self.sid].amount

        to_buy = +self.get_amount(ub) - current_amount
        to_sell = -self.get_amount(lb) - current_amount

        for order in orders.filter(status=["New", "PreSubmitted"], type=["STP"]):
            if order.amount > 0:
                self.update_order(order, stop_price=ub, amount=to_buy)
            if order.amount < 0:
                self.update_order(order, stop_price=lb, amount=to_sell)

        if not orders:
            if current_amount >= 0:
                self.stop_order(to_sell, lb)
            if current_amount <= 0:
                self.stop_order(to_buy, ub)
