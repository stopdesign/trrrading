from trader.data_types import Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import MBB
from trader.strategy import BaseStrategy

"""


macd = fast_ma - slow_ma

basis = sma(macd, length)
dev = mult * stdev(macd, length)

upper = basis + dev
lower = basis - dev

longCondition = crossover(macd, lower)
shortCondition = crossunder(macd, upper)
"""

class MBM_01(BaseStrategy):
    """
    Стратегия MACD vs BB.
    """

    algo = {"strategy": "Adaptive"}

    def on_start(self):
        # Параметры стратегии
        tf = self.params.timeframe
        length = self.params.length
        length_ma_1 = self.params.length_ma_1
        length_ma_2 = self.params.length_ma_2
        mult = self.params.mult

        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=False, on_bar=self.on_bar)

        # Консолидатор данных в более крупный таймфрейм
        self.ind_tf = Consolidator(self.data_1m, tf)

        # Инициализация индикаторов
        self.mbb = MBB(
            self.ind_tf,
            skip_extra_hours=False,
            length=length,
            fast_length=length_ma_1,
            slow_length=length_ma_2,
            mult=mult,
        )

    def get_amount(self, price=None):
        # Подсчет размера позиции
        return 10
        # return int(100_000 / price)

    def on_bar(self, trade: Trade):
        if not (self.warmed and self.mbb.ready):
            return

        # Не торговать, если уже есть ордер
        if self.orders.filter(self.sid).active():
            self.log.warn(f"{self.sid}, strategy has live order")
            return

        mbb = self.mbb.value

        long = mbb["long"]
        short = mbb["short"]

        current_amount = self.positions[self.sid].amount

        order_amount = 0

        if current_amount <= 0 and long:
            order_amount = +self.get_amount() - current_amount

        if current_amount >= 0 and short:
            order_amount = -self.get_amount() - current_amount

        if abs(order_amount) > 0:
            order = Order(self.sid, "MKT", order_amount, ib_algo=self.algo)
            self.place_order(order)
