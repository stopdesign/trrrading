import numpy as np
import pandas as pd
import scipy.stats
from termcolor import cprint, colored
from strategy import Signal
from trader import Trader
from io import StringIO


class Tester(Trader):

    def start(self, loop=None):
        # Нужно получить достаточно данных, чтобы стратегия смогла
        # восстановить последний торговый сигнал.
        invalid_advisor = False
        for advisor in self.get_advisors():
            if advisor.state not in [Signal.LONG, Signal.SHORT]:
                invalid_advisor = True
                cprint(f" NO STATE: {advisor} ", color="red", attrs=["reverse"])

        if not invalid_advisor:
            self.exchange.start_listen(self.on_event, loop)

    def get_stats(self, test_name=""):

        pf = self.gross_profit / abs(self.gross_loss) if self.gross_loss else 0
        p = self.exchange.net_value - self.exchange.cash_initial
        roi = p / self.exchange.cash_initial * 100
        trades = self.trades_count["buy"] + self.trades_count["sell"]
        
        # R2
        x = np.arange(len(self.deposits))
        y = np.array(self.deposits, dtype=float)
        slope, intercept, r_value, p_value, std_err = scipy.stats.linregress(x, y)
        r2 = r_value ** 2
        roi_dd = roi / self.max_drawdown

        txt = (
            f"ROI: {roi:+0.1f}%\t "
            f"Max DD: {self.max_drawdown:0.1f}%\t "
            f"ROI/DD: {roi_dd:0.2f}\t "
            f"PF: {pf:0.2f}\t "
            f"R²: {r2:0.2f}\t "
            f"Trades: {trades:0.0f}\t "
        )
        cprint(txt)

        with open(f"../res/{test_name}-stats.csv", "w+") as s:
            df = pd.read_csv(StringIO(self.log_stats), index_col="Date")
            df.index = pd.to_datetime(df.index)
            df = df.resample("1d").pad()
            df["Change"] = df["Value"].pct_change(periods=10).dropna()
            df.to_csv(s)

        return (
            roi,
            self.max_drawdown,
            trades,
            pf,
            r2,
            roi_dd,
        )
