import logging

from trader.data_types import Bar, Order, Trade
from trader.exchange import Consolidator, Data
from trader.indicator import HullMA, MovingAverage

from .base import BaseStrategy

log = logging.getLogger("strategy")


class GHS1(BaseStrategy):
    """
    Стратегия для зерновых фьючерсов.
    """

    def on_start(self):
        self.length = 180

        # Подписка на данные
        self.data_1m = Data(self.sid, rth=1, on_bar=self.on_bar, on_tick=self.on_tick)

        # Подписка на производный таймфрейм
        self.data_10m = Consolidator(self.data_1m, "10m")

        # Добавление индикатораов
        self.ma = MovingAverage(self.data_1m, interval=10)
        self.hma = HullMA(self.data_10m, interval=self.length)

    def on_bar(self, bar: Bar):
        # print("GHS1 on_bar")
        pass

    def on_bar_5m(self, bar: Bar):
        # print("GHS1 on_bar_5m")
        pass

    def market_order(self, amount):
        order = Order(self.sid, type="market", amount=amount)
        self.place_order(order)

    def on_tick(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        if not self.warmed:
            return

        if len(self.hma.values) < 5 or not self.hma.values[-5]["hma"]:
            log.error(f"{trade.date}, Indicator wasn't warmed up?")
            return

        hma = self.hma.values

        hma_now = hma[-1]["hma"]
        hma_prev = hma[-3]["hma"]

        current_amount = self.positions[self.sid].amount
        target_amount = current_amount

        diff = abs(hma_now - hma_prev) / hma_now * 100

        if current_amount <= 0 and hma_now > hma_prev and diff > 0.01:
            target_amount = +int(100_000 / trade.price)

        if current_amount >= 0 and hma_now < hma_prev and diff > 0.01:
            target_amount = -int(100_000 / trade.price)

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        # log.info(f"STRATEGY ON ORDER: {payload}")
        pass
