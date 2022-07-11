import json
import logging
import os
from csv import QUOTE_NONNUMERIC, DictReader
from datetime import datetime, timezone

import pandas as pd
import redis

from market_calendar import MarketCalendar

r = redis.Redis(host="localhost", port=6379, db=0)


log = logging.getLogger("polygon_adapter")


symbols = [
    "AAPL.NASDAQ",
    # "MES.GLOBEX",
    # "MNQ.GLOBEX",
    # "MNTS.NASDAQ",
    "URA.ARCA",
    "REMX.ARCA",
]


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class PolygonAdapter:
    def __init__(self, offline=True, api_key=None, path=None):
        self.offline = offline
        self.api_key = api_key
        self.path = path

    def load_from_path(self, symbol, dt_1, dt_2, path):
        data = []
        ts_1, ts_2 = dt_to_ts(dt_1), dt_to_ts(dt_2)
        with open(f"{path}{symbol}.csv") as f:
            csv = f.readlines()
            fields = csv.pop(0).strip().split(",")
            reader = DictReader(csv, fields, quoting=QUOTE_NONNUMERIC)
            for row in reader:
                row["t"] = int(row["t"])
                if ts_1 <= row["t"] <= ts_2:
                    data.append(row)
        return data

    def load_from_file(self, symbol, dt_1, dt_2):
        data = []
        date_x = datetime(2022, 1, 1)
        path = os.path.abspath(self.path)
        if dt_1 < date_x or dt_2 < date_x:
            data += self.load_from_path(symbol, dt_1, dt_2, f"{path}/pre_2022/")
        if dt_1 >= date_x or dt_2 >= date_x:
            data += self.load_from_path(symbol, dt_1, dt_2, f"{path}/2022/")
        return data

    def load(self, symbols, dt_1, dt_2):
        all_data = []

        self.schedule = MarketCalendar(symbols, dt_1, dt_2)

        for symbol in list(symbols):
            ss = symbol.split(".")[0]

            if self.offline:
                data = self.load_from_file(ss, dt_1, dt_2)
            else:
                data = self.load_from_api(ss, dt_1, dt_2)

            line_by_ts = {}
            for line in data:
                payload = {
                    "dt": ts_to_dt(line["t"]),
                    "o": line["o"],
                    "h": line["h"],
                    "l": line["l"],
                    "c": line["c"],
                    "vol": line["v"],
                    "symbol": symbol,
                }
                line_by_ts[line["t"]] = payload

            # Минутная сетка
            grid = pd.date_range(dt_1, dt_2, freq="T")

            prev_line = None

            for row in grid:
                ts = int(row.timestamp())
                dt = row.to_pydatetime()

                line = line_by_ts.get(ts)

                is_open = self.schedule.is_open(symbol, dt)
                is_rth = self.schedule.is_rth(symbol, dt)

                if line:
                    res = line
                else:
                    # if is_rth:
                        # log.warning(f"No data in RTH: {symbol}, {dt}")
                    if is_open:
                        if prev_line:
                            # Повтор предыдущего значения
                            res = {
                                "dt": dt,
                                "o": prev_line["c"],
                                "h": prev_line["c"],
                                "l": prev_line["c"],
                                "c": prev_line["c"],
                                "vol": 0,
                                "symbol": symbol,
                            }
                        else:
                            res = {"dt": dt, "empty": 1}
                    else:
                        res = {"dt": dt, "closed": 1}

                if is_open:
                    prev_line = line or prev_line
                else:
                    prev_line = None

                all_data.append((ts, symbol, res))

        log.info(f"{symbols}, {dt_1}, {dt_2}, {len(all_data)}")

        return sorted(all_data)


def process_trades(symbol):
    key = f"{symbol}:TRADES"

    dt_1 = datetime(2022, 1, 1)
    dt_2 = datetime.utcnow()

    pa = PolygonAdapter(path="../../data/polygon_nyse/")
    data = pa.load([symbol], dt_1, dt_2)

    for ts, _, line in data:
        data_str = json.dumps(line, indent=None, separators=(",", ":"), default=str)
        # print(data_str)
        r.zadd(key, {data_str: ts})


def main():
    for symbol in symbols:
        print(symbol)
        process_trades(symbol)


if __name__ == "__main__":
    main()
