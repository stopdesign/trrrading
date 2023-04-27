from zoneinfo import ZoneInfo

from trader.data_types import Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import HullMA, MovingAverage
from trader.strategy import BaseStrategy


class GHS_01(BaseStrategy):
    """
    Стратегия для зерновых фьючерсов.
    """

    algo = {"strategy": "Adaptive"}

    def on_start(self):
        # Параметры стратегии
        tf = self.params.timeframe
        length = self.params.length
        len_ma_1 = self.params.length_ma_1
        len_ma_2 = self.params.length_ma_2

        # Подписка на данные
        self.data_1m = Data(self.sid, rth=True, on_tick=self.on_tick)

        # Подписка на производный таймфрейм
        self.data_tf = Consolidator(self.data_1m, tf, filter=self.liquid_hours)

        # Добавление индикатораов
        self.ma_1 = MovingAverage(self.data_1m, length=len_ma_1)
        self.ma_2 = MovingAverage(self.data_1m, length=len_ma_2)
        self.hma = HullMA(
            self.data_tf,
            length=length,
            skip_extra_hours=True,
            skip_empty=True,
        )

    def liquid_hours(self, bar):
        """
        Основные торговые часы зерновых фьючерсов.
        """
        dt = bar.date.replace(tzinfo=ZoneInfo("UTC"))
        dt_ex = dt.astimezone(ZoneInfo("America/Chicago"))
        return bar.rth and (6 <= dt_ex.hour <= 13)

    def get_amount(self, price):
        # Подсчет размера позиции
        return int(100_000 / price)

    def on_tick(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        if not (self.warmed and self.hma.ready):
            return

        # Не торговать, если уже есть ордер
        if self.orders.filter(self.sid).active():
            self.log.warn(f"{self.sid}, strategy has live order")
            return

        hma = self.hma.value["hma"]
        prev_hma = self.hma.value["prev_hma"]

        current_amount = self.positions[self.sid].amount
        target_amount = current_amount

        diff = abs(hma - prev_hma) / hma * 100
        ma_diff = abs(self.ma_1.value["ma"] - self.ma_2.value["ma"])

        filter = ma_diff > 0.5 and diff > 0.001

        if current_amount <= 0 and hma > prev_hma and filter:
            target_amount = +self.get_amount(trade.price)

        if current_amount >= 0 and hma < prev_hma and filter:
            target_amount = -self.get_amount(trade.price)

        if target_amount != current_amount:
            amount = target_amount - current_amount
            order = Order(self.sid, type="MKT", amount=amount, ib_algo=self.algo)
            self.place_order(order)
