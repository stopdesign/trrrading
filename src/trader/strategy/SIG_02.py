from trader.data_types import Order
from trader.exchange import Data
from trader.strategy import BaseStrategy

ALGO = {"strategy": "Adaptive"}


class SIG_02(BaseStrategy):
    """
    Стратегия Channel Breakout.
    """

    def on_start(self):
        # Подписка на данные через callback-функции
        self.data_1m = Data(self.sid, rth=True)

    def get_amount(self):
        return 1

    def on_signal(self, payload: dict):
        if not (self.warmed and payload):
            return

        # Не торговать, если уже есть ордер
        if a := self.orders.filter(self.sid).active():
            self.log.warn(f"{self.sid}, strategy has live order, {a}")
            return

        current_amount = self.positions[self.sid].amount

        self.log.info(f"pos: {current_amount}, sig: {payload}")

        position = int(payload.get("position", 0))

        amount = position - current_amount

        if abs(amount) > 0:
            order = Order(self.sid, "MKT", int(amount))
            self.place_order(order)
