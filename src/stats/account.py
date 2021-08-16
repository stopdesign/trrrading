import pandas as pd
import numpy as np
import scipy.stats
from decimal import Decimal
from exchange import BaseExchange
from termcolor import cprint, colored


class AccountStats:
    def __init__(self, exchange: BaseExchange, target_margin):
        self.exchange = exchange
        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.prev_net_value = self.exchange.net_value
        self.deposits = [self.exchange.cash_initial]
        self.target_margin = target_margin
        self.stats = []

    def on_trade(self, symbol, payload):
        self.trades_count[payload["side"]] += 1

    def update_pl(self):
        diff_value = self.exchange.net_value - self.prev_net_value
        self.gross_profit += max(0, diff_value)
        self.gross_loss += min(0, diff_value)
        self.prev_net_value = self.exchange.net_value

    def snapshot(self):
        net = self.exchange.net_value
        drawdown = max(Decimal(0), self.max_net_value - net)
        self.max_net_value = max(self.max_net_value, net)
        self.cur_drawdown = drawdown / self.max_net_value * 100
        self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)
        self.deposits.append(net)

        def get_margin_for_position(position):
            amount = position["amount"]
            price = position["price"]
            margin_level = self.exchange.get_margin_level(amount < 0)
            return abs(float(amount)) * float(price) * margin_level if price else None

        margin_used = 0
        # TODO: вынести margin_used в self.exchange
        for symbol, position in self.exchange.get_positions().items():
            margin_used += get_margin_for_position(position)

        # TODO: добавить проверку на main session
        if self.exchange.dt_last and net:
            self.stats.append({
                "date": self.exchange.dt_last,
                "net_value": net,
                "drawdown": self.cur_drawdown,
                "margin_used": margin_used,
            })

    def to_csv(self, file_name):
        if self.stats:
            df = pd.DataFrame(self.stats)
            df = df.set_index("date")
            df.to_csv(file_name)
        else:
            open(file_name, "w").close()

    def print_summary(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]))

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]

        # Не уверен, что это можно считать ROI, но это профит
        # на единицу задействованных в торговле денег.
        roi = p / self.target_margin * 100

        # R2
        if self.deposits and len(self.deposits) > 1:
            x = np.arange(len(self.deposits))
            y = np.array(self.deposits, dtype=float)
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)
            r2 = r_value ** 2
        else:
            r2 = 0
            self.max_drawdown = 0

        ml = self.exchange.margin_rule['long'] * 100
        ms = self.exchange.margin_rule['short'] * 100

        txt = (
            "\n"
            f"{self.exchange.dt_start}\n"
            f"{self.exchange.dt_last}\n"
            "\n"
            f"Margin long:  {ml:0.0f}%\n"
            f"Margin short: {ms:0.0f}%\n"
            "\n"
            f"ROI: {roi:+7.1f}%\n"
            f"Max DD: {self.max_drawdown:4.1f}%\n"
            f"PF: {pf:9.2f}\n"
            f"R²: {r2:9.2f}\n"
            f"Trades: {trades:5.0f}\n"
            f"GP: {self.gross_profit:+9.0f}\n"
            f"GL: {self.gross_loss:+9.0f}"
        )
        cprint(txt)
