#!python3

import json
import fileinput
from decimal import Decimal


def add(timestamp, price, symbol, q=None):
    if q is not None:
        price = price.quantize(q)
    price_str = str(price)
    if "." in price_str:
        price_str = price_str.rstrip("0")
    return {
        "timestamp": timestamp,
        "price": price_str,
        "symbolId": symbol,
    }


def interval_to_trades(interval):
    m = 1000

    t = interval["timestamp"]

    s = interval["symbolId"]

    l = Decimal(interval["low"])
    h = Decimal(interval["high"])
    o = Decimal(interval["open"])
    c = Decimal(interval["close"])

    longest_exp = min(
        o.as_tuple().exponent,
        h.as_tuple().exponent,
        l.as_tuple().exponent,
        c.as_tuple().exponent,
    )
    q = Decimal(10) ** longest_exp

    # open
    trades = [add(t, o, s)]

    if c != o:
        if c > o:
            # print("^^^")
            l_, h_ = l, h
        else:
            # print("vvv")
            l_, h_ = h, l

        trades.append(add(t + 10 * m, o - (o - l_) * 3 / 4, s, q))
        trades.append(add(t + 15 * m, o - (o - l_) * 1 / 2, s, q))

        trades.append(add(t + 20 * m, l_, s))

        trades.append(add(t + 25 * m, l_ + (h_ - l_) * 1 / 3, s, q))
        trades.append(add(t + 30 * m, l_ + (h_ - l_) * 2 / 3, s, q))

        trades.append(add(t + 40 * m, h_, s))

        trades.append(add(t + 45 * m, h_ - (h_ - c) * 3 / 4, s, q))
        trades.append(add(t + 50 * m, h_ - (h_ - c) * 1 / 2, s, q))
    else:
        # print("===")
        trades.append(add(t + 20 * m, l, s))
        trades.append(add(t + 40 * m, h, s))

    # close
    trades.append(add(t + 55 * m, c, s))

    return trades


def ohlc_to_trades(intervals):
    trades = []
    for interval in intervals:
        trades += interval_to_trades(interval)
    return trades


def ohlc_to_quotes(intervals):
    quotes = []
    for interval in intervals:
        trades = interval_to_trades(interval)
        for trade in trades:
            quotes.append({
                "timestamp": trade["timestamp"],
                "ask": [{"price": trade["price"], "size": 1}],
                "bid": [{"price": trade["price"], "size": 1}],
                "symbolId": trade["symbolId"],
            })
    return quotes


def main():

    for line in fileinput.input():

        interval = json.loads(line)

        trades = interval_to_trades(interval)

        for trade in trades:
            print(json.dumps(trade, indent=None, default=str))


if __name__ == "__main__":
    main()
