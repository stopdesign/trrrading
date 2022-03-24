import logging
import numpy as np
import scipy.stats
from decimal import Decimal
from termcolor import cprint, colored

log = logging.getLogger("pf_stats")


class PortfolioStats:
    def __init__(self, trader, portfolio, cash_initial):
        self.trader = trader
        self.portfolio = portfolio
        self.exchange = portfolio.exchange
        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.cash_initial = cash_initial
        self.prev_net_value = cash_initial
        self.deposits = [cash_initial]
        self.stats = []
        self.slippage = 0
        self.fee = 0

    def snapshot(self):
        net = self.portfolio.get_virtual_net_value() + self.cash_initial

        if not (self.exchange.dt_last and net):
            return

        drawdown = max(Decimal(0), self.max_net_value - net)
        self.max_net_value = max(self.max_net_value, net)
        self.cur_drawdown = drawdown / self.max_net_value * 100
        self.max_drawdown = max(self.max_drawdown, self.cur_drawdown)
        self.deposits.append(net)

        margin_used = 0

        self.stats.append({
            "date": self.exchange.dt_last,
            "net_value": net,
            "drawdown": self.cur_drawdown,
            "margin_used": margin_used,
        })

    def portfolio_info(self):
        symbols = sorted(list({s.symbol for s in self.portfolio.strategies}))
        for symbol in symbols:
            amount = self.portfolio.get_total_amount(symbol)
            log.info(colored(f"Target: {symbol}, {amount:+0.0f}", "cyan"))

    def account_info(self):
        bot_margin = 0
        log.info(colored(f"Net Value:   {self.prev_net_value:6.0f}", "blue"))
        log.info(colored(f"Margin Used: {bot_margin:6.0f}\n", "blue"))

    def print_summary(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]) + "\n")

        print(self.portfolio.get_info())

        # Посчитать итоговый Net Value — это просто cash_initial плюс весь профит
        net = self.portfolio.get_virtual_net_value() + self.cash_initial

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = net - self.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]

        # Не уверен, что это можно считать ROI, но это профит
        # на единицу задействованных в торговле денег.
        roi = p / self.cash_initial * 100

        if p:
            rel_fee = -self.fee / float(p) * 100
        else:
            rel_fee = float("nan")

        # R2
        if self.deposits and len(self.deposits) > 1:
            x = np.arange(len(self.deposits))
            y = np.array(self.deposits, dtype=float)
            slope, _, r_value, p_value, std_err = scipy.stats.linregress(x, y)
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
            f"Start:     {self.trader.dt_start.date()}\n"
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
