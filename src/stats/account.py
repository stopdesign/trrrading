import logging
import pandas as pd
import numpy as np
import scipy.stats
from collections import defaultdict
from decimal import Decimal
from exchange import BaseExchange
from termcolor import cprint, colored
from exchange.utils.nyse_cal import trading_session

log = logging.getLogger("account")


class AccountStats:
    def __init__(self, trader, exchange: BaseExchange):
        self.trader = trader
        self.exchange = exchange
        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.prev_net_value = self.exchange.net_value
        self.deposits = [self.exchange.cash_initial]
        self.stats = []
        self.slippage = 0
        self.fee = 0

    def on_trade_done(self, _, payload):
        self.trades_count[payload["side"]] += 1
        self.slippage += payload["slippage"]
        self.fee += payload["fee"]
        self.update_pl()

    def update_pl(self):
        diff_value = self.exchange.net_value - self.prev_net_value
        self.gross_profit += max(0, diff_value)
        self.gross_loss += min(0, diff_value)
        self.prev_net_value = self.exchange.net_value

    def snapshot(self):
        net = self.exchange.net_value

        if not (self.exchange.dt_last and net):
            return

        if trading_session(self.exchange.dt_last) != "main":
            return

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

        self.stats.append({
            "date": self.exchange.dt_last,
            "net_value": net,
            "drawdown": self.cur_drawdown,
            "margin_used": margin_used,
        })

    def to_csv(self, file_name):
        df = pd.DataFrame.from_records(self.stats, index=["date"], coerce_float=True)
        df.to_csv(file_name, float_format="%.2f")

    def advisors_info(self):
        # Только для тестов
        for advisor in self.trader.get_advisors():
            print(advisor.info)

    def settings_info(self):
        # Только для тестов
        txt = (
            f"{type(self.exchange).__name__}, "
            # f"Target margin: {self.trader.target_margin}\n"
            # f"Can short: {self.trader.can_short}\n"
            f"{self.exchange.margin!r}, "
            f"{self.exchange.fee!r}\n"
        )
        print(txt)

    def print_short_summary(self):
        advisor = self.trader.get_advisors()[0]

        if not self.deposits:
            print(f"SKIP   {advisor.instrument:<10}  {advisor.strategy!r}")

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]
        roi = p / self.trader.target_margin * 100
        rel_max_drawdown = roi / self.max_drawdown
        txt = (
            f"ROI:{roi:6.1f}%   "
            f"RMD:{rel_max_drawdown:5.1f}   "
            f"DD:{self.max_drawdown:5.1f}%   "
            f"PF:{pf:6.2f}   "
            f"TR:{trades:>4}   "
            f"{advisor.instrument:<10}  "
            f"{advisor.strategy!r}"
        )
        print(txt)

    def print_summary(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]) + "\n")

        self.settings_info()
        self.advisors_info()

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]

        # Не уверен, что это можно считать ROI, но это профит
        # на единицу задействованных в торговле денег.
        roi = p / self.trader.target_margin * 100

        rel_fee = -self.fee / float(p) * 100

        # R2
        if self.deposits and len(self.deposits) > 1:
            x = np.arange(len(self.deposits))
            y = np.array(self.deposits, dtype=float)
            slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)
            r2 = r_value ** 2
            gp = float(self.gross_profit)
            rel_slpg = self.slippage / (gp + self.slippage) * 100 if gp else 0
        else:
            r2 = 0
            self.max_drawdown = 0
            rel_slpg = 0

        if self.exchange.dt_last:
            end = self.exchange.dt_last.date()
        else:
            end = "—"

        txt = (
            "\n"
            f"Start:     {self.exchange.dt_start.date()}\n"
            f"End:       {end!s:>10}\n"
            "---------------------\n"
            f"ROI:      {roi:+10.1f}%\n"
            f"Max Drawdown:  {self.max_drawdown:5.1f}%\n"
            f"Profit Factor: {pf:6.2f}\n"
            f"R²:            {r2:6.2f}\n"
            f"Trades:    {trades:10.0f}\n"
            f"Fee:         {rel_fee:+7.1f}%\n"
            f"Slippage:    {rel_slpg:7.1f}%\n"
        )
        cprint(txt)

    def get_margin_for_position(self, _, position):
        amount = position["amount"]
        price = position["price"]
        # price = self.exchange.get_price(instrument, "mid")
        margin_level = self.exchange.get_margin_level(amount < 0)
        return abs(float(amount)) * float(price) * margin_level if price else None

    def portfolio_info(self):
        positions = defaultdict(dict)

        for symbol, value in self.exchange.get_positions().items():
            positions[symbol] = value
            positions[symbol]["advised"] = self.trader.get_advised_position(symbol)

        for symbol in self.exchange.symbols:
            if symbol not in positions:
                positions[symbol] = {
                    "advised": self.trader.get_advised_position(symbol),
                    "price": self.exchange.get_price(symbol, "mid"),
                    "amount": 0,
                }

        total_margin_used = 0

        txt = colored("Positions:    ", "blue")
        for symbol, position in sorted(positions.items()):
            if position["advised"] is not None:
                advised = "{0:+0.0f}".format(position["advised"])
                total_margin_used += self.get_margin_for_position(symbol, position)
                cur = float(position['amount'])
                adv = float(position['advised'])
                rel_diff = abs(cur - adv) / abs(cur + adv) if cur + adv else 0
                color = "cyan" if rel_diff < 0.05 else "yellow"
            else:
                advised = "-"
                color = "white"
            amount = position.get('amount') or 0
            txt += colored(
                f"{symbol}  "
                f"cur: {amount:+0.0f}, "
                f"adv: {advised};  ",
                color,
            )
        log.info(txt)

        log.info(colored(f"Net Value:   {self.exchange.net_value:6.0f}", "blue"))
        log.info(colored(f"Margin Used: {total_margin_used:6.0f}", "blue"))

        if hasattr(self.exchange, "real_margin"):
            log.info(colored(f"Margin Real: {self.exchange.real_margin:6.0f}", "blue"))
