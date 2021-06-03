from collections import defaultdict
from decimal import Decimal
from strategy import Signal
from util import trades_to_decimal_ohlc, normalize_ohlc


class BaseStrategy:

    historical = []
    interval_size = 60

    def __init__(self):
        pass

    def add_to_historical(self, data):
        self.historical += data

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
            # print("last_known_interval TS:", ts)
            trades_by_interval[ts] = [
                {"timestamp": ts, "price": last_known_interval["open"], "size": "1"},
                {"timestamp": ts, "price": last_known_interval["high"], "size": "1"},
                {"timestamp": ts, "price": last_known_interval["low"], "size": "1"},
                {"timestamp": ts, "price": last_known_interval["close"], "size": "1"},
            ]

        ts_q = trade["timestamp"] // (1000 * self.interval_size)
        trades_by_interval[ts_q * 1000 * self.interval_size].append(trade)

        ohlc_by_interval = list(map(trades_to_decimal_ohlc, trades_by_interval.items()))

        # self.historical += normalize_ohlc(ohlc_by_interval)
        # self.add_to_historical(normalize_ohlc(ohlc_by_interval))
        self.add_to_historical(ohlc_by_interval)

    def test(self, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после получения новых данных.
        """
        raise NotImplementedError()
