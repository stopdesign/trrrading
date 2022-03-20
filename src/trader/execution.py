import logging
from datetime import timezone
from decimal import Decimal
from exchange import BaseExchange
from main.models import Instrument, Order, Position
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
        self.portfolio = portfolio

    def apply_targets(self, dt):

        target_positions = dict(self.portfolio.positions)
        # actual_positions = dict(self.exchange.get_positions())

        for symbol in self.exchange.instruments:
            actual = self.get_actual_position_amount(symbol)
            # actual = actual_positions.get(symbol, {}).get("amount", 0)

            target = target_positions.get(symbol, {}).get("amount")
            signal_price = target_positions.get(symbol, {}).get("signal_price", 0)

            if target is None:
                # log.debug(colored(f"SKIP {symbol}: no target amount, {dt}", "magenta"))
                continue

            side = None
            order_amount = abs(actual - target)

            if actual < target:
                side = "buy"
            elif actual > target:
                side = "sell"

            if not side:
                # log.debug(colored(f"SKIP {symbol}: no change, {dt}", "magenta"))
                continue

            # Посчитать ордеры в стадии исполнения
            amount_in_orders = 0
            if not self.run.backtest:
                amount_in_orders = self.get_amount_in_orders(symbol)

            log.info(colored(
                f"APPLY {symbol}, actual: {actual}, target: {target}, "
                f"in_orders: {amount_in_orders}", "magenta"
            ))

            if amount_in_orders:
                log.warning(colored(f"Active orders: {symbol} {amount_in_orders}, SKIP", "red"))
                continue

            log.warning(colored(f"Create order: {symbol} {order_amount}", "blue", attrs=['reverse']))
            order = self.create_order(dt, symbol, side, order_amount, signal_price)

            if self.run.backtest:
                self.emulate_execution(order)

    def get_actual_position_amount(self, symbol):
        if self.run.backtest:
            return self.exchange.positions.get(symbol, {}).get("amount")

        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)
        orders_after_start = Order.objects.filter(
            account=self.run.account,
            id__gt=self.exchange.latest_order_id,
            instrument=instrument,
        )

        # Позиция, сохраненная при запуске скрипта
        amount = self.exchange.positions.get(symbol, {}).get("amount")

        for order in orders_after_start:
            if order.action == Order.Side.buy:
                amount += order.filled
            if order.action == Order.Side.sell:
                amount -= order.filled

        return amount

    def emulate_execution(self, order):

        symbol = order.ticker

        actual_positions = dict(self.exchange.get_positions())
        actual = actual_positions.get(symbol, {}).get("amount", 0)

        side = str(order.action).lower()

        # Здесь эмулируется исполнение ордера
        fill_price = self.exchange.get_price(symbol, "mid")
        fill_price = Decimal(str(fill_price))
        order.simulate_fill(fill_price)

        # где-то тут должно быть фейковое изменение cash и margin used
        # При полном или частичном закрытии позиции считается профит.
        if side == "sell":
            delta = -order.amount
        else:
            delta = order.amount

        amount = delta
        position = self.exchange.positions[symbol]
        trade_profit = 0

        # Позиция и дельта не 0 и имеют разный знак
        if actual * delta < 0:
            # Частичное закрытие позиции
            amount_to_close = min(abs(actual), abs(delta))

            if side == "sell":
                amount_to_close = -amount_to_close

            # log.info(f"amount_to_close: {amount_to_close}")

            # Одно с другим сокращается на partial_close_amount
            amount -= amount_to_close
            position["amount"] += amount_to_close

            # Записать профит от закрытия позиции
            trade_profit = amount_to_close * (position["price"] - fill_price)
            self.exchange.cash += trade_profit

            # # Если amount еще остался — открыть позицию
            if amount != 0:
                self.exchange.positions[symbol] = {
                    "amount": amount,
                    "price": fill_price,
                }
        else:
            # log.info(f"amount_to_open: {order_amount}")
            # Увеличение позиции в ту же сторону
            total_value = position["amount"] * position["price"]
            total_value += amount * Decimal(fill_price)
            total_amount = position["amount"] + amount
            av_price = total_value / total_amount
            self.exchange.positions[symbol] = {
                "amount": total_amount,
                "price": av_price,
            }

        # Событие «успешное завершение сделки»
        payload = {
            "side": side,
            "amount": order.amount,
            "price": fill_price,
            "profit": trade_profit,
            "slippage": 0,
            "fee": 0,
            "net_value": self.exchange.net_value,
        }
        dt = order.created_at.replace(tzinfo=None)
        self.exchange.on_event("after_trade", dt, symbol, payload)

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

    def create_order(self, dt, symbol, side, order_amount, signal_price):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)

        txt = f"TRADE: {dt}  {side:>4} {symbol} {order_amount} @ {signal_price}"
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
