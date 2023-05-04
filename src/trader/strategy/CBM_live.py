from trader.data_types import Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import DonchianChannels, MovingAverage
from trader.strategy import BaseStrategy

ALGO = {"strategy": "Adaptive"}


class CBM_live(BaseStrategy):
    """
    Стратегия Channel Breakout.
    """

    length: int
    length_ma: int = 50
    timeframe: str = "10m"
    rth_data: bool = True
    amount: int = 1

    def on_start(self):
        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=self.rth_data, on_tick=self.on_tick)

        # Консолидатор данных в более крупный таймфрейм
        self.ind_tf = Consolidator(self.data_1m, self.timeframe)

        # Инициализация индикаторов
        self.ma = MovingAverage(self.ind_tf, length=self.length_ma)
        self.dc = DonchianChannels(self.ind_tf, length=self.length)

    def get_amount(self, price) -> int:
        # Подсчет размера позиции
        if self.amount > 0:
            return self.amount
        else:
            return int(100_000 / price)

    def on_tick(self, trade: Trade):
        if not (self.warmed and self.dc.ready):
            return

        # Не торговать, если уже есть ордер
        if self.orders.filter(self.sid).active():
            self.log.warn(f"{self.sid}, strategy has live order")
            return

        ub, lb = self.dc.value["ub"], self.dc.value["lb"]

        current_amount = self.positions[self.sid].amount

        amount = 0

        if current_amount <= 0 and trade.price > ub:
            amount = +self.get_amount(ub) - current_amount

        if current_amount >= 0 and trade.price < lb:
            amount = -self.get_amount(lb) - current_amount

        if abs(amount) > 0:
            order = Order(self.sid, "MKT", int(amount), ib_algo=ALGO)
            self.place_order(order)
