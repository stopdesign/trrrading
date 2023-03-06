from dataclasses import dataclass, asdict
from indicator.donchian_channels import DonchianChannels
from strategy import BaseStrategy, Signal
from data_types import Bar, Trade
import logging


log = logging.getLogger("strategy")


# @dataclass(slots=True)
# class Bar2(Bar):
#     """
#     Добавляю индикаторы, которые будут сохранены в файл.
#     """
#     up: float = None
#     dn: float = None


@dataclass(slots=True)
class Order:
    amount: int
    status: str
    fill_price: float = None


class ChBr(BaseStrategy):

    def on_start(self):

        self.dc = DonchianChannels(self.length)

        self.symbol = "URA.ARCA"

    def market_order(self, amount):
        order = Order(amount=amount, status="new")
        self.exchange.place_order(order)

    def on_bar(self, bar: Bar):

        pass
        # # Класс, сохраняющий индикаторы
        # bar = Bar2(**asdict(bar))

        # self.data.append(bar)
        
        # if not self.warmed:
        #     return

    def on_trade(self, trade: Trade):
        """
        Проверить сигнал стратегии при появлении новой цены.
        """
        bar = self.data[-1] if self.data else None

        if not self.warmed:
            return

        if not bar or not bar.dn:
            return

        if not (trade.rth and bar.rth):
            return

        for order in self.exchange.orders:
            if order.status == "new":
                return

        position = self.exchange.positions.get(self.symbol)

        current_amount = position if position else 0
        target_amount = current_amount

        if current_amount <= 0 and trade.price > bar.up:
            target_amount = +10            

        if current_amount >= 0 and trade.price < bar.dn:
            target_amount = -10

        if target_amount != current_amount:
            self.market_order(target_amount - current_amount)

    def on_order_event(self, payload):
        log.info(f"STRATEGY ON ORDER: {payload}")
        pass
