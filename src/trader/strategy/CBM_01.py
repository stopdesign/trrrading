from trader.data_types import Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels, MovingAverage
from trader.strategy import BaseStrategy


class CBM_01(BaseStrategy):
    """
    Стратегия Channel Breakout.
    """

    algo = {"strategy": "Adaptive"}

    def on_start(self):
        # Параметры стратегии
        length = self.params.length
        length_ma = self.params.length_ma

        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=True, on_tick=self.on_tick)

        # Консолидатор данных в более крупный таймфрейм
        self.ind_tf = Consolidator(self.data_1m, "15m")

        # Инициализация индикаторов
        self.ma = MovingAverage(self.data_1m, length=length_ma)
        self.dc = DonchianChannels(self.data_1m, length=length)

    def get_amount(self, price):
        # Подсчет размера позиции
        return 1
        # return int(100_000 / price)

    def on_tick(self, trade: Trade):
        if not (self.warmed and self.dc.ready):
            return

        # Не торговать, если уже есть ордер
        if self.orders.filter(self.sid).active():
            self.log.warn(f"{self.sid}, strategy has live order")
            return

        ub, lb = self.dc.value["ub"], self.dc.value["lb"]

        current_amount = self.positions[self.sid].amount

        order_amount = 0

        if current_amount <= 0 and trade.price > ub:
            order_amount = +self.get_amount(ub) - current_amount

        if current_amount >= 0 and trade.price < lb:
            order_amount = -self.get_amount(lb) - current_amount

        if abs(order_amount) > 0:
            order = Order(self.sid, "MKT", order_amount, ib_algo=self.algo)
            self.place_order(order)
