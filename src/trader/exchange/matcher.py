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
        execute = False
        price = None

        side = "buy" if order.amount > 0 else "sell"

        if order.type == "market":
            execute = True
            price = self.exchange.get_price(order.sid, side)  # "mid"

        if order.type == "limit":
            pass

        if order.type == "stop":
            # TODO: сделать нормальный алгоритм
            bar = self.exchange.bars[order.sid][-1]

            for price in {bar.open, bar.high, bar.low, bar.close}:
                price = Decimal(price)
                if order.amount > 0 and price >= order.stop_price:
                    execute = True
                    break
                if order.amount < 0 and price <= order.stop_price:
                    execute = True
                    break

        if execute and price:
            order.status = "filled"
            order.fill_price = price

            # обновить позицию
            position = self.exchange.positions[order.sid]

            new_amount = position.amount + order.amount
            trade_profit = position.update(new_amount, price)

            # обновить баланс
            self.exchange.account["net_value"] += trade_profit

            profit_str = f"{trade_profit:+9.2f}"
            if trade_profit > 0:
                profit_str = colored(profit_str, "green")
            if trade_profit < 0:
                profit_str = colored(profit_str, "red")

            dt = self.exchange.dt_last.replace(second=0)
            log.info(
                f"Fill {order.local_id}, {dt}  "
                f"{side.upper():>4} {order.sid:>10},  "
                f"amnt: {abs(order.amount):6.0f},  "
                f"price: {order.fill_price:0.2f},  "
                f"trade: {profit_str},  "
                f"net: {self.exchange.account['net_value']:10.2f} "
            )

            # сохранить результаты сделки для статистики
            # total_profit_rel = 100 * self.total_profit / cash_per_strategy
            # profit_rel = 100 * profit / cash_per_strategy
            data = {
                "dt": self.exchange.dt_last,
                "time": dt_to_ts(self.exchange.dt_last),
                "ms": order.strategy.market_system,
                "sid": order.sid,
                "side": side,
                "amount": abs(order.amount),
                "profit": trade_profit,
                "profit_rel": 0,  # f"{profit_rel:0.4f}",
                "price": price,
            }
            self.exchange.trades.append(data)

            # сообщить стратегии о срабатывании ордера
            self.exchange.on_event("order", dt=self.exchange.dt_last, payload=order)
