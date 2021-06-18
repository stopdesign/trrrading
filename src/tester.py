import sys
from datetime import datetime, timezone
from decimal import Decimal
from termcolor import cprint, colored
from advisor import Advisor
from exchange import BacktestExchange
from strategy import Signal
from trader import Trader


CURSOR_UP_ONE = "\x1b[1A"
ERASE_LINE = "\x1b[2K"


class Tester(Trader):

    def __init__(self, advisors):
        # super().__init__()

        self.log_intervals = "Date,Open,High,Low,Close\n"
        self.log_trades = "Date,Direction,Price\n"
        self.log_stats = "Date,Value,Drawdown\n"

        self.can_short = True

        self.advisors = advisors

        symbols_to_track = list(set([a.instrument for a in self.advisors]))

        self.exchange = BacktestExchange(
            symbols_to_track,
            dt_start=datetime(2020, 12, 28).astimezone(timezone.utc),
            cash=Decimal("10000"),
        )

        # Прогнать события по историческим данным.
        # Предзаполняются цены и сигналы, торговля не происходит.
        self.exchange.process_historical_data(self.on_event)

        self.max_net_value = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")
        self.cur_drawdown = 0
        self.gross_profit = 0
        self.gross_loss = 0
        self.trades_count = {"buy": 0, "sell": 0, "close": 0}
        self.prev_net_value = self.exchange.net_value

    def start(self, loop=None):
        # Нужно получить достаточно данных, чтобы стратегия смогла
        # восстановить последний торговый сигнал.
        invalid_advisor = False
        for advisor in self.get_advisors():
            if advisor.state not in [Signal.LONG, Signal.SHORT]:
                invalid_advisor = True
                # cprint(f" NO STATE: {advisor} ", color="red", attrs=["reverse"])

        if not invalid_advisor:
            self.exchange.start_listen(self.on_event, loop)

    def get_stats(self):
        cprint(
            f"net: {self.exchange.net_value:0.0f}  "
            f"cur dd: {self.cur_drawdown:4.1f}%  "
            f"max dd: {self.max_drawdown:4.1f}%  "
            f"gp: {self.gross_profit:+0.0f}  "
            f"gl: {self.gross_loss:+0.0f}  "
        )
        return (
            self.exchange.net_value,
            self.max_drawdown,
            self.gross_profit,
            self.gross_loss,
            self.trades_count,
        )
