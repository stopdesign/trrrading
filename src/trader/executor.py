import logging
from datetime import timezone
from decimal import Decimal
from main.models import Instrument, Order, Position
from termcolor import colored
from trader import Exchange

log = logging.getLogger("execution")


class Executor:
    """
    Применение Target Positions к реальному миру.
    """
    exchange: Exchange

    def __init__(self, exchange, portfolio, run):
        self.run = run
        self.exchange = exchange
        self.account = run.account
        self.portfolio = portfolio
        self.latest_order_id = None
        self.real_positions = {}
        self.update_portfolio()

    def update_portfolio(self):
        """
        Для торговли через брокера позиции выставляются по значениям из базы.

        TODO: предупреждения про устаревшие данные
        """
        self.latest_order_id = Order.objects.latest('id').id

        # Инструменты из конфига устанавливаются в 0
        for strategy in self.portfolio.strategies:
            self.real_positions[strategy.symbol] = {
                "amount": Decimal(0),
                "price": Decimal("nan"),
                "dt": None,
            }

        # Для торговли через брокера позиции выставляются по значениям из базы
        for position in Position.objects.filter(account=self.account):
            symbol = position.instrument.ticker
            self.real_positions[symbol] = {
                "amount": position.amount,
                "price": position.avg_price,
                "dt": position.updated_at,
            }

    def apply_targets(self, dt):

        symbols = sorted(list({s.symbol for s in self.portfolio.strategies}))

        for symbol in symbols:
            actual = self.get_actual_position_amount(symbol)
            target = self.portfolio.get_total_amount(symbol)

            # TODO: проброс signal_price
            signal_price = Decimal(0)

            if target is None:
                log.debug(colored(f"SKIP {symbol}: no target amount, {dt}", "magenta"))
                continue

            side = None
            order_amount = abs(actual - target)

            if actual < target:
                side = "buy"
            elif actual > target:
                side = "sell"

            if not side:
                log.debug(colored(f"SKIP {symbol}: no change, {dt}", "magenta"))
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
            # self.create_order(dt, symbol, side, order_amount, signal_price)

    def get_actual_position_amount(self, symbol):

        # Позиция, сохраненная при запуске скрипта
        amount = self.real_positions.get(symbol, {}).get("amount")

        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Instrument.objects.get(symbol=stock_symbol)
        orders_after_start = Order.objects.filter(
            account=self.account,
            id__gt=self.latest_order_id,
            instrument=instrument,
        )

        for order in orders_after_start:
            if order.action == Order.Side.buy:
                amount += order.filled
            if order.action == Order.Side.sell:
                amount -= order.filled

        return amount

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
