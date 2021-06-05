from collections import defaultdict
from decimal import Decimal
from termcolor import cprint
from exchange import ExanteExchange, BacktestExchange


class Broker:
    def __init__(self, symbols):
        self.positions = defaultdict(Decimal)
        self.exchange = BacktestExchange(symbols=",".join(symbols))
        self.cash = None
        self._positions_info()
        self._check_orders()

    def _positions_info(self):
        # Cache position and cash info
        self.positions = self.exchange.get_positions()
        self.cash = self.exchange.get_cash_value()  # // 100  # допустим, торгуем на 1%

        cprint(f"\nCash: {self.cash}\n", attrs=["bold"])

    def _check_orders(self):
        orders = self.exchange.load_last_orders()
        if orders:
            print()
            cprint("WARNING: there are active orders:", "red")
        for order in orders:
            op = order["orderParameters"]
            side = op["side"]
            symbol = op["symbolId"]
            quantity = op["quantity"]
            status = order["orderState"]["status"]
            cprint(f"ORDER: {side} {symbol} {quantity} [{status}]", "yellow")

    def get_current_position(self, symbol):
        return self.positions.get(symbol, Decimal("0"))

    def adjust_portfolio(self, side, asset_amount_diff, instrument):
        """
        Синхронно создать ордер и дождаться исполнения.
        Обновить данные о портфолио.
        """
        if side == "buy":
            self.positions[instrument] += asset_amount_diff
        if side == "sell":
            self.positions[instrument] -= asset_amount_diff

        self.exchange.create_order(side, asset_amount_diff, instrument)

        self._positions_info()
