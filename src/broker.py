from collections import defaultdict
from decimal import Decimal
from termcolor import cprint
from exchange import ExanteExchange


def _():
    pass


class Broker:
    def __init__(self, symbols):
        self.positions = defaultdict(Decimal)
        self.symbols = symbols
        symbols_str = ",".join(symbols)
        self.exchange = ExanteExchange(
            on_trade=_, on_quote=_, on_interval=_, symbol=symbols_str
        )
        self.cash = None
        self.update_positions()
        self.check_orders()

    def update_positions(self):
        ai = self.exchange.load_account_info()

        self.cash = Decimal(ai["netAssetValue"]) // 100  # допустим, торгуем на 1%

        print()
        cprint(f"Cash: {self.cash}", attrs=["bold"])
        print()

        cprint(f"Positions:", attrs=["bold"])
        pos = defaultdict(Decimal)
        for position in ai["positions"]:
            value = Decimal(position["convertedValue"])
            quantity = Decimal(position['quantity'])
            pos[position["symbolId"]] = quantity
            if quantity or value:
                cprint(
                    f"{position['symbolId']:<10} "
                    f"{quantity:>+15.0f} "
                    f"{value:>+15.2f}"
                )
        self.positions = pos
        print()

    def check_orders(self):
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

    # def get_current_value(self, symbol):
    #     return self.asset_values.get(symbol, Decimal("0"))

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

        self.update_positions()
