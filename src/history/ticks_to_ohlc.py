#!python3

import json
import fileinput
from collections import defaultdict
from decimal import Decimal


def trades_to_decimal_ohlc(item: dict) -> dict:
    """
    Конвертер формата: list of trades >> OHLC
    """
    timestamp, trades = item
    prices = [Decimal(t["price"]) for t in trades]
    res = {
        # "dt": datetime.fromtimestamp(timestamp // 1000),
        "timestamp": timestamp,
        "open": prices[0],
        "low": min(prices),
        "close": prices[-1],
        "high": max(prices),
    }
    return res


def main():

    # file = "../data/live-COPX.ARCA-trades-ticks.jsonl"
    file = "data.jsonl"
    interval_size = 60

    trades_by_interval = defaultdict(list)

    for line in fileinput.input():
        line = line.replace("'", '"')
        trade = json.loads(line)
        ts = trade["timestamp"]
        ts_q = ts // (1000 * interval_size) * interval_size
        trades_by_interval[ts_q * 1000].append(trade)

    ohlc = list(map(trades_to_decimal_ohlc, trades_by_interval.items()))

    ohlc = sorted(ohlc, key=lambda x: x["timestamp"])

    for line in ohlc:
        print(json.dumps(line, indent=None, default=str))


if __name__ == "__main__":
    main()
