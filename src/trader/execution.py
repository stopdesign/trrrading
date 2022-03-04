import logging
from datetime import timezone
from decimal import Decimal
from exchange import BaseExchange
from main.models import Instrument, Order
from termcolor import colored

log = logging.getLogger("execution")


class Execution:
    """
    Применение Target Positions к реальному миру.
    """
    exchange: BaseExchange

    def __init__(self, exchange, portfolio, run):
        self.run = run
        self.exchange = exchange
        self.account = run.account
        self.target_positions = portfolio.positions
        self.actual_positions = self.exchange.get_positions()

    def apply_targets(self, dt):

        # что на самом деле есть в портфолио
        self.actual_positions = self.exchange.get_positions()

        for symbol in self.exchange.instruments:
            actual = self.actual_positions.get(symbol, {}).get("amount", 0)
            target = self.target_positions.get(symbol, 0)

            # if dt > self.exchange.dt_start:
            #     log.info(f"POSITIONS {symbol} actual={actual} target={target}")

            side = None
            order_amount = abs(actual - target)

            if actual < target:
                side = "buy"
            elif actual > target:
                side = "sell"

            if not side:
                continue

            # Проверить ордеры, которые выставлены и ждут исполнения
            # TODO: в будущем нужно добавлять/отменять ордер в этом случае
            if not self.run.backtest:
                if amount_in_orders := self.get_amount_in_orders(symbol):
                    log.warning(f"Active orders: {symbol} {amount_in_orders}")
                    continue

            order = self.create_order(dt, symbol, side, order_amount)

            if self.run.backtest:
                fill_price = self.exchange.get_price(symbol, "mid")
                fill_price = Decimal(str(fill_price))
                order.simulate_fill(fill_price)

                self.exchange.positions[symbol] = {
                    "amount": target,
                    "price": fill_price,
                }

    def get_amount_in_orders(self, symbol):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        orders = Order.objects.filter(account=self.account, instrument=instrument)
        orders = orders.exclude(status__in=["Filled", "Cancelled", "Inactive"])

        in_active_orders = 0
        for order in orders:
            in_active_orders += order.amount - order.filled

        assert in_active_orders >= 0
        return in_active_orders

    def create_order(self, dt, symbol, side, order_amount):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        # TODO: пробросить откуда-то
        signal_price = self.exchange.get_price(symbol, "mid")

        txt = f"TRADE: {dt}  {side}  {symbol} {order_amount} @ {signal_price}"
        log.info(colored(txt, color="cyan"))

        # Шаблон ордера
        order = Order.market_order(
            self.account,
            self.run,
            instrument,
            side.upper(),
            order_amount,
        )
        order.signal_price = signal_price
        order.created_at = dt.replace(tzinfo=timezone.utc)
        order.save()

        return order
