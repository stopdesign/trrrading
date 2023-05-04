from zoneinfo import ZoneInfo

from trader.data_types import Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import HullMA, MovingAverage
from trader.strategy import BaseStrategy

ALGO = {"strategy": "Adaptive"}


class GHS_live(BaseStrategy):
    """
    Стратегия для зерновых фьючерсов.
    """

    length: int = 150
    length_ma_1: int = 0
    length_ma_2: int = 0
    timeframe: str = "10m"
    rth_data: bool = True
    amount: int = 1

    def on_start(self):
        # Подписка на данные
        self.data_1m = Data(self.sid, rth=self.rth_data, on_tick=self.on_tick)

        # Подписка на производный таймфрейм
        self.data_tf = Consolidator(
            self.data_1m,
            self.timeframe,
            filter=self.liquid_hours,
        )

        # Добавление индикатораов
        self.hma = HullMA(
            self.data_tf,
            length=self.length,
            skip_extra_hours=self.rth_data,
            skip_empty=True,
        )
        if self.length_ma_1:
            self.ma_1 = MovingAverage(self.data_1m, length=self.length_ma_1)
        if self.length_ma_2:
            self.ma_2 = MovingAverage(self.data_1m, length=self.length_ma_2)

    def liquid_hours(self, bar):
        """
        Основные торговые часы зерновых фьючерсов.
        """
        dt = bar.date.replace(tzinfo=ZoneInfo("UTC"))
        dt_ex = dt.astimezone(ZoneInfo("America/Los_Angeles"))
        return bar.rth and (6 <= dt_ex.hour <= 11)

    def get_amount(self, price) -> int:
        # Подсчет размера позиции
        if self.amount > 0:
            return self.amount
        else:
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

        current_amount = int(self.positions[self.sid].amount)
        target_amount = current_amount

        if self.length_ma_1 and self.length_ma_2:
            diff = abs(hma - prev_hma) / hma * 100
            ma_diff = abs(self.ma_1.value["ma"] - self.ma_2.value["ma"])
            do_trade = ma_diff > 0.5 and diff > 0.001
        else:
            do_trade = True

        if current_amount <= 0 and hma > prev_hma and do_trade:
            target_amount = +self.get_amount(trade.price)

        if current_amount >= 0 and hma < prev_hma and do_trade:
            target_amount = -self.get_amount(trade.price)

        if target_amount != current_amount:
            amount = target_amount - current_amount
            order = Order(self.sid, type="MKT", amount=amount, ib_algo=ALGO)
            self.place_order(order)
