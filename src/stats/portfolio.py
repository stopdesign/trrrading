import json
import os.path
import logging
import numpy as np
from decimal import Decimal
from termcolor import cprint, colored

log = logging.getLogger("pf_stats")


class PortfolioStats:
    """
    История работы бэктеста по всему портфолио.
    Значения сохраняются при при вызове snapshot.
    print_summary выводит таблицу с итогами работы бэктеста.
    """

    def __init__(self, trader, exchange, cash_initial):
        self.trader = trader
        self.exchange = exchange
        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.max_trade_drawdown = Decimal("-Infinity")
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
        net = self.exchange.get_net_value()

        if not (self.exchange.dt_last and net):
            return

        drawdown = max(Decimal(0), self.max_net_value - net)
        self.max_net_value = max(self.max_net_value, net)
        self.cur_drawdown = drawdown / self.cash_initial * 100
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
        """
        Вывести список позиций.
        """
        symbols = sorted(list({s.symbol for s in self.trader.strategies}))
        for symbol in symbols:
            if p := self.exchange.positions.get(symbol):
                log.info(colored(f"Position: {symbol}, {p.amount:+0.0f}", "cyan"))
            else:
                log.info(colored(f"Position: {symbol}, unknown", "yellow"))

    def account_info(self):
        bot_margin = 0
        log.info(colored(f"Net Value:   {self.prev_net_value:6.0f}", "blue"))
        log.info(colored(f"Margin Used: {bot_margin:6.0f}\n", "blue"))

    # def save_events(self, base_dir):
    #     """
    #     Сохранение сделок на диск.
    #     """
    #     for strategy in self.portfolio.strategies:
    #         strategy_name = type(strategy).__name__
    #         file_name = f"{strategy.symbol}_{strategy_name}_events.jsonl"
    #         path = os.path.join(base_dir, file_name)
    #         txt = ""
    #         events = self.portfolio.events[strategy.market_system]
    #         for event in events:
    #             txt += json.dumps(event, default=str) + "\n"
    #         with open(path, "w") as f:
    #             f.write(txt)

    def print_summary(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]) + "\n")

        # print(self.portfolio.get_info())

        net = self.exchange.get_net_value()

        for trade in self.exchange.trades:
            if trade["profit"] > 0:
                self.gross_profit += trade["profit"]
            else:
                self.gross_loss += trade["profit"]
            self.trades_count[trade["side"]] += 1

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = net - self.cash_initial
        trades = sum(self.trades_count.values())

        # Не уверен, что это можно считать ROI, но это профит
        # на единицу задействованных в торговле денег.
        roi = p / self.cash_initial * 100

        # if p:
        #     rel_fee = -self.fee / float(p) * 100
        # else:
        #     rel_fee = float("nan")

        # R²
        if self.deposits and len(self.deposits) > 1:
            x = np.arange(len(self.deposits))
            y = np.array(self.deposits, dtype=float)
            if len(set(y)) > 1:
                r2 = np.corrcoef(x, y)[0, 1] ** 2
            else:
                r2 = float("nan")
            # gp = float(self.gross_profit)
            # rel_slpg = self.slippage / (gp + self.slippage) * 100 if gp else 0
        else:
            r2 = float("nan")
            self.max_drawdown = 0
            # rel_slpg = 0

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
            # f"Fee:         {rel_fee:+7.1f}%\n"
            # f"Slippage:    {rel_slpg:7.1f}%\n"
        )
        cprint(txt)
