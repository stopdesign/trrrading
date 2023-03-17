import logging
from datetime import timezone
from decimal import Decimal

from termcolor import colored

from trader.data_types import Order

log = logging.getLogger("matcher")


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class LocalMatcher:
    """
    Исполняет ордер локально, используя исторические цены.

    Что здесь нужно?

    Position
        В реальной торговле position будет содержать дополнительную информацию:
            amount
            avg_price
            unrealized_pnl
        Для бэктеста в позиции может быть полезно держать статистику,
        но нужно ли делать это здесь?

    Order
        Ордер и его свойства.

    Account
        Параметры депозита


    Что будет происходить

    При поступлении новых торговых данных нужно попробовать исполнить ордеры,
    которые лежат в статусе new. Метод process_order принимает ордер и пытается
    его исполнить. Класс знает текущие позиции и цены. Класс делает всё,
    что происходило бы при реальном исполнении: меняет позиции, статус ордера, депозит.

    Цену исполнения ордера считает exchange, наверное, т.к. там этот метод нужен
    для других задач. Matcher занимается только изменением значений.

    """

    def __init__(self, exchange):
        self.exchange = exchange

    def process_order(self, order: Order):
        """
        Тип ордера: market, limit, stop.
        """
        process_order = False
        price = None

        instrument = order.instrument

        side = "buy" if order.amount > 0 else "sell"

        if order.type == "market":
            process_order = True
            price = self.exchange.get_price(instrument, side)  # "mid"

        if order.type == "limit":
            pass

        if order.type == "stop":
            # TODO: сделать нормальный алгоритм
            price = self.exchange.get_price(instrument, "mid")
            if order.amount > 0 and price > order.stop_price:
                process_order = True
                # price = Decimal(order.stop_price)
                # price = (Decimal(order.stop_price) + Decimal(price)) / 2
            if order.amount < 0 and price < order.stop_price:
                process_order = True
                # price = Decimal(order.stop_price)
                # price = (Decimal(order.stop_price) + Decimal(price)) / 2

        if process_order and price:
            order.status = "filled"
            order.fill_price = price

            # log.info(f"FILL {order}")

            # обновить позицию
            position = self.exchange.positions.get(instrument)

            new_amount = position.amount + order.amount
            trade_profit = position.update(new_amount, price)

            # обновить баланс
            self.exchange.account["net_value"] += trade_profit

            profit_str = f"{trade_profit:+9.2f}"
            if trade_profit > 0:
                profit_str = colored(profit_str, "green")
            if trade_profit < 0:
                profit_str = colored(profit_str, "red")

            log.info(
                f"Fill {order.local_id}, {side:>4}, price: {order.fill_price:0.2f}, "
                f"trade: {profit_str}, "
                f"net: {self.exchange.account['net_value']:10.2f} "
            )

            # сохранить результаты сделки для статистики
            # total_profit_rel = 100 * self.total_profit / cash_per_strategy
            # profit_rel = 100 * profit / cash_per_strategy
            data = {
                "dt": self.exchange.dt_last,
                "time": dt_to_ts(self.exchange.dt_last),
                "symbol": order.instrument,
                "side": side,
                "amount": abs(order.amount),
                "profit": trade_profit,
                "profit_rel": 0, # f"{profit_rel:0.4f}",
                "price": price,
            }
            self.exchange.trades.append(data)

            # сообщить стратегии о срабатывании ордера
            self.exchange.on_event("order", dt=self.exchange.dt_last, payload=order)
