from datetime import datetime, timedelta, timezone

from trader.data_types import Bar, Order
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels
from trader.strategy import BaseStrategy


class CBS_01(BaseStrategy):
    """
    Стратегия Channel Breakout на Stop-ордерах.
    """

    length: int
    timeframe: str = "10m"
    rth_data: bool = True
    rth_order: bool = True

    def on_start(self):
        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=self.rth_data, on_bar=self.on_bar)

        # Консолидатор данных в более крупный таймфрейм
        self.ind_data = Consolidator(self.data_1m, self.timeframe)

        # Инициализация индикаторов
        self.dc = DonchianChannels(
            self.ind_data,
            length=self.length,
            skip_extra_hours=self.rth_data,
        )

    def get_amount(self, price):
        # Подсчет размера позиции
        return 1
        # return int(100_000 / price)

    def stop_order(self, amount, stop_price, limit_price):
        order = Order(
            self.sid,
            type="STP LMT",
            amount=amount,
            stop_price=stop_price,
            limit_price=limit_price,
            rth=self.rth_order,
        )
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

        b = +self.get_amount(ub) - current_amount
        s = -self.get_amount(lb) - current_amount

        # Обновляемые ордеры
        for o in orders.filter(status=["New", "PreSubmitted"], type=["STP LMT"]):
            if o.amount > 0:
                self.update_order(o, stop_price=ub, limit_price=ub + 1, amount=b)
            if o.amount < 0:
                self.update_order(o, stop_price=lb, limit_price=lb - 1, amount=s)

        if not orders:
            if current_amount >= 0:
                self.stop_order(s, lb, lb - 1)
            if current_amount <= 0:
                self.stop_order(b, ub, ub + 1)
