import logging
import pandas as pd
import numpy as np
import scipy.stats
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
            level = self.exchange.get_margin_level(amount < 0)
            return abs(float(amount)) * float(price) * level if price else None

        margin_used = 0
        # TODO: вынести margin_used в self.exchange
        for symbol, position in self.exchange.get_positions().items():
            margin_used += get_margin_for_position(position) or Decimal(0)

        self.stats.append({
            "date": self.exchange.dt_last,
            "net_value": net,
            "drawdown": self.cur_drawdown,
            "margin_used": margin_used,
        })

    def to_csv(self, file_name):
        df = pd.DataFrame.from_records(self.stats, index=["date"], coerce_float=True)
        df.to_csv(file_name, float_format="%.2f")

    def strategies_info(self):
        # Только для тестов
        for strategy in self.trader.strategies:
            print(strategy)

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
        """
        Для пакетного тестирования, когда тестируется только одна стратегия.
        """
        advisor = self.trader.get_advisors()[0]

        if not self.deposits:
            print(f"SKIP   {advisor.symbol:<10}  {advisor.strategy!r}")

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]
        roi = p / self.trader.target_margin * 100
        rel_max_drawdown = roi / self.max_drawdown

        # R2
        if self.deposits and len(self.deposits) > 1:
            x = np.arange(len(self.deposits))
            y = np.array(self.deposits, dtype=float)
            _, _, r_value, p_value, std_err = scipy.stats.linregress(x, y)
            r2 = r_value ** 2
        else:
            r2 = 0
            self.max_drawdown = 0

        txt = (
            f"ROI:{roi:6.1f}%   "
            f"RMD:{rel_max_drawdown:5.1f}   "
            f"DD:{self.max_drawdown:5.1f}%   "
            f"PF:{pf:6.2f}   "
            f"R²:{r2:6.2f}   "
            f"TR:{trades:>4}   "
            f"{advisor.symbol:<10}  "
            f"{advisor.strategy!r}"
        )
        print(txt)
        return roi

    def print_summary(self):
        cprint("\n" + colored(" RESULTS ", attrs=["reverse"]) + "\n")

        self.settings_info()
        self.strategies_info()

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        trades = self.trades_count["buy"] + self.trades_count["sell"]

        # Не уверен, что это можно считать ROI, но это профит
        # на единицу задействованных в торговле денег.
        roi = p / self.trader.target_margin * 100

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

    def positions_extra(self):
        """
        Добавляет advised_position к позициям портфолио.
        Объединяет реальные позиции у брокера (по которым нет advised)
        и позиции из конфига бота (по которым может не быть чего-то еще).
        """

        # Позиции, реально открытые у брокера
        positions = self.exchange.get_positions()

        # Инструменты, которые есть в конфиге, но не у брокера
        for symbol in self.exchange.symbols:
            if symbol not in positions:
                mid_price = self.exchange.get_price(symbol, "mid")
                if mid_price is not None:
                    mid_price = Decimal(str(self.exchange.get_price(symbol, "mid")))
                else:
                    mid_price = Decimal(0)
                positions[symbol] = {
                    "amount": Decimal(0),
                    # бесполезно, т.к. цены в этом случае не будет у биржи
                    "price": mid_price,
                    "daily_pnl": float("nan"),
                }

        for symbol, position in positions.items():
            position["symbol"] = symbol
            position["advised"] = self.trader.portfolio.positions[symbol].get("amount")

        return positions

    def get_margin_used_by_bot(self):
        """
        Примерно (криво) считает margin, использованный для позиций бота.
        """
        total_margin_used = 0
        for symbol, position in self.exchange.get_positions().items():
            mp = self.get_margin_for_position(symbol, position)
            if mp is not None:
                total_margin_used += mp
            else:
                log.error(f"get_margin_for_position is None, {symbol}, {position}")
        return total_margin_used

    def portfolio_info(self):
        positions = self.positions_extra()
        res = colored("Positions:", "blue")
        for symbol, position in sorted(positions.items()):
            txt = f"{symbol}, cur: {position['amount']}, adv: {position['advised']};"
            color = "cyan" if position["advised"] is not None else "white"
            res += "  " + colored(txt, color)
        log.info(res)

    def account_info(self):
        bot_margin = self.get_margin_used_by_bot()

        log.info(colored(f"Net Value:   {self.exchange.net_value:6.0f}", "blue"))
        log.info(colored(f"Margin Used: {bot_margin:6.0f}", "blue"))

        if hasattr(self.exchange, "real_margin"):
            log.info(colored(f"Margin Real: {self.exchange.real_margin:6.0f}", "blue"))
