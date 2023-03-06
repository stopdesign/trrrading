import logging
from datetime import timezone
from decimal import Decimal
from main.models import Contract, Order, Position
from termcolor import colored
# from storage.redis import check_open_time
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
        self.initial_positions = {}
        self.update_portfolio()

    def update_portfolio(self):
        """
        Для торговли через брокера позиции выставляются по значениям из базы.

        TODO: предупреждения про устаревшие данные
        """
        try:
            self.latest_order_id = Order.objects.latest('id').id
        except Order.DoesNotExist:
            self.latest_order_id = 0

        # Инструменты из конфига устанавливаются в 0
        for strategy in self.portfolio.strategies:
            self.initial_positions[strategy.symbol] = {
                "amount": Decimal(0),
                "price": Decimal("nan"),
                "dt": None,
            }

        # Для торговли через брокера позиции выставляются по значениям из базы
        for position in Position.objects.filter(account=self.account):
            symbol = position.instrument.ticker
            self.initial_positions[symbol] = {
                "amount": position.amount,
                "price": position.avg_price,
                "dt": position.updated_at,
            }

    def apply_targets(self, dt):

        symbols = sorted(list({s.symbol for s in self.portfolio.strategies}))

        for symbol in symbols:

            # Проверить режим работы биржи.
            # Если биржа не торгует, то ордер не выставляется.
            # Если это премаркет или постмаркет, то засисит от настроек, наверное.
            exchange_symbol = symbol.split(".")[1]
            # is_rth = check_open_time(exchange_symbol, dt)
            is_rth = True  # FIXME

            if not is_rth:
                # txt = f"{symbol} market is closed, {dt} signal"
                # log.debug(colored(txt, "white"))
                continue

            actual = self.get_actual_position_amount(symbol)
            target = self.portfolio.get_total_amount(symbol)

            if target.is_nan():
                log.error(colored(f"SKIP {symbol}: no target amount, {dt}", "red"))
                continue

            # TODO: проброс signal_price
            signal_price = Decimal(0)

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
            amount_in_orders = self.get_amount_in_orders(symbol)

            txt = colored(
                f"APPLY {symbol}, actual: {actual}, target: {target}, "
                f"in_orders: {amount_in_orders}", "cyan"
            )
            if amount_in_orders:
                txt += colored(f" — ACTIVE ORDERS, SKIP", "red")
            log.warning(colored(txt, "red"))

            if amount_in_orders:
                continue

            self.create_order(dt, symbol, side, order_amount, signal_price)

    def get_actual_position_amount(self, symbol):
        """
        Берутся позиции из базы на момент старта скрипта,
        добавляются значения из всех исполненных с того момента ордеров.
        """

        # Позиция, сохраненная при запуске скрипта
        amount = self.initial_positions.get(symbol, {}).get("amount")

        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Contract.objects.get(symbol=stock_symbol)
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
        instrument = Contract.objects.get(symbol=stock_symbol)

        orders = Order.objects.filter(account=self.account, instrument=instrument)
        orders = orders.exclude(status__in=["Filled", "Cancelled", "Inactive"])

        in_active_orders = 0
        for order in orders:
            in_active_orders += order.amount - order.filled

        assert in_active_orders >= 0
        return in_active_orders

    def create_order(self, dt, symbol, side, order_amount, signal_price):
        stock_symbol, exchange_symbol = symbol.split(".")
        instrument = Contract.objects.get(symbol=stock_symbol)

        txt = f"TRADE: {side.upper():>4} {symbol} {order_amount} @ {signal_price}"
        log.info(colored(txt, color="cyan", attrs=["reverse"]))

        # Шаблон ордера
        order = Order.adaptive_market_order(
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
