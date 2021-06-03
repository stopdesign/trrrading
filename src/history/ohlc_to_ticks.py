#!python3

import json
import fileinput
from decimal import Decimal


def add(timestamp, price, q=None):
    if q is not None:
        price = price.quantize(q)
    price_str = str(price)
    if "." in price_str:
        price_str = price_str.rstrip("0")
    return {
        "timestamp": timestamp,
        "price": price_str,
    }


def main():

    m = 1000

    for line in fileinput.input():

        interval = json.loads(line)

        t = interval["timestamp"]

        l = Decimal(interval["low"])
        h = Decimal(interval["high"])
        o = Decimal(interval["open"])
        c = Decimal(interval["close"])

        longest_exp = min(
            o.as_tuple().exponent,
            h.as_tuple().exponent,
            l.as_tuple().exponent,
            c.as_tuple().exponent
        )
        q = Decimal(10) ** longest_exp

        # open
        trades = [add(t, o)]

        if c != o:
            if c > o:
                # print("^^^")
                l_, h_ = l, h
            else:
                # print("vvv")
                l_, h_ = h, l

            trades.append(add(t + 10 * m, o - (o - l_) * 3 / 4, q))
            trades.append(add(t + 15 * m, o - (o - l_) * 1 / 2, q))

            trades.append(add(t + 20 * m, l_))

            trades.append(add(t + 25 * m, l_ + (h_ - l_) * 1 / 3, q))
            trades.append(add(t + 30 * m, l_ + (h_ - l_) * 2 / 3, q))

            trades.append(add(t + 40 * m, h_))

            trades.append(add(t + 45 * m, h_ - (h_ - c) * 3 / 4, q))
            trades.append(add(t + 50 * m, h_ - (h_ - c) * 1 / 2, q))
        else:
            # print("===")
            trades.append(add(t + 20 * m, l))
            trades.append(add(t + 40 * m, h))

        # close
        trades.append(add(t + 55 * m, c))

        for trade in trades:
            print(json.dumps(trade, indent=None, default=str))


if __name__ == "__main__":
    main()
