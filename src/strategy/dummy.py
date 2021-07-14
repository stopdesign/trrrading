import math
from collections import defaultdict
from strategy import BaseStrategy, Signal
from util import trades_to_ohlc


class Dummy(BaseStrategy):
    intraday_only = False
    arr_lo = []
    arr_hi = []

    def __init__(self, **params):
        super().__init__()
        self.interval_size = params.get("interval", 3600)

    def __str__(self):
        return f"<Dummy strategy for historical data>"

    def update_trades(self, trade: dict) -> None:
        """
        Добавить новые сделки к историческим данным.

        historical — это список OHLC по интервалам.
        Интервалы создаются, даже если в этот период не было сделок.
        """
        trades_by_interval = defaultdict(list)

        # Смикшировать последний интервал и новую сделку
        if self.historical:
            last_known_interval = self.historical.pop()
            ts = last_known_interval["timestamp"]
            trades_by_interval[ts] = [
                {"price": last_known_interval["open"], "size": "1"},
                {"price": last_known_interval["high"], "size": "1"},
                {"price": last_known_interval["low"], "size": "1"},
                {"price": last_known_interval["close"], "size": "1"},
            ]

        ts_q = math.ceil(trade["timestamp"] / (1000 * self.interval_size))
        # ts_q = math.ceil((trade["timestamp"] + 30 * 60 * 1000) / (1000 * self.interval_size))
        ts_r = int(ts_q * 1000 * self.interval_size)
        trades_by_interval[ts_r].append(trade)

        self.historical += list(map(trades_to_ohlc, trades_by_interval.items()))

    def test_price(self, *args) -> Signal:
        return Signal.CLOSE
