import json
import redis
from datetime import datetime, timezone
from storage.ib import load_many


r = redis.Redis(host='localhost', port=6379, db=6)


symbols = [
    # "AAPL.NASDAQ",
    "MES.GLOBEX",
    # "MNQ.GLOBEX",
    # "MNTS.NASDAQ",
    # "URA.ARCA",
]

TRADES_NUM_COL = ["open", "high", "low", "close", "volume", "average", "barCount"]
BIDASK_NUM_COL = ["av_bid", "max_ask", "min_bid", "av_ask"]


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def load(symbol, data_type):
    start = datetime(2022, 1, 1).date()
    df = load_many([symbol], [data_type], start=start)

    # BIDASK должен приходить раньше TRADES для этого интервала
    return df.sort_values(["date", "ticker", "data_type"])


def process_trades(symbol):
    key = f"{symbol}:TRADES"
    df = load(symbol, "TRADES")

    del df["ticker"]
    del df["data_type"]
    data = df.to_dict(orient="index")

    # print(json.dumps(data, indent=2, default=str))

    for i, line in list(data.items()):
        dt = i.to_pydatetime()
        ts = dt_to_ts(dt)
        line["rth"] = int(line["rth"])
        data = {
            "dt": dt,
            "o": line["open"],
            "h": line["high"],
            "l": line["low"],
            "c": line["close"],
            "vol": line["volume"],
            "avg": line["average"],
            "cnt": line["barCount"],
            "rth": int(line["rth"]),
        }
        data_str = json.dumps(data, indent=None, separators=(',', ':'), default=str)
        # data_str = data_str.replace('"', "'")
        r.zadd(key, {data_str: ts})


def process_quotes(symbol):
    key = f"{symbol}:QUOTES"
    df = load(symbol, "BIDASK")

    del df["ticker"]
    del df["data_type"]
    data = df.to_dict(orient="index")

    for i, line in list(data.items()):
        dt = i.to_pydatetime()
        ts = dt_to_ts(dt)
        line["rth"] = int(line["rth"])
        data = {
            "dt": dt,
            "av_bid": line["av_bid"],
            "max_ask": line["max_ask"],
            "min_bid": line["min_bid"],
            "av_ask": line["av_ask"],
            "rth": int(line["rth"]),
        }
        data_str = json.dumps(data, indent=None, separators=(',', ':'), default=str)
        # data_str = data_str.replace('"', "'")
        r.zadd(key, {data_str: ts})


def main():
    for symbol in symbols:
        print(symbol)
        process_trades(symbol)
        process_quotes(symbol)


if __name__ == "__main__":
    main()
