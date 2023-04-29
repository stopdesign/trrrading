import logging
import os
from csv import QUOTE_NONNUMERIC, DictReader
from datetime import datetime, timezone
from time import sleep

import requests
from termcolor import cprint

from .base_source import BaseSource

log = logging.getLogger("polygon_adapter")


BASE_URL = f"https://api.polygon.io/v2/aggs/ticker"
LIMIT = 50000


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class PolygonAdapter(BaseSource):
    def __init__(self, offline=True, api_key=None, path="./"):
        self.offline = offline
        self.api_key = api_key
        self.path = os.path.abspath(path)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(offline={self.offline})"

    def load_from_api(self, symbol, dt_1, dt_2):
        ts_1 = dt_to_ts(dt_1) * 1000
        ts_2 = dt_to_ts(dt_2) * 1000

        limit = LIMIT
        data = []

        while True:
            url = f"{BASE_URL}/{symbol}/range/1/minute/{ts_1}/{ts_2}"
            params = {
                "apiKey": self.api_key,
                "adjusted": False,
                "sort": "asc",
                "limit": limit,
            }
            r = requests.get(url, params=params, timeout=5)

            if r.status_code == 429:
                cprint("API limit, wait 10 sec...", "yellow")
                sleep(10)
                continue

            try:
                rj = r.json()
            except Exception as e:
                cprint(str(e), "red")
                cprint(f"API request error: {r.status_code}, {r.text}", "red")
                raise Exception("PolygonApiError")

            if err := rj.get("error"):
                cprint(f"API error: {err}", "red")
                raise Exception("PolygonApiError")

            res = rj.pop("results", [])
            data += res

            if len(res):
                max_ts_collected = int(res[-1]["t"]) + 1000 * 60
                if len(res) < limit or max_ts_collected >= ts_2:
                    break
                ts_1 = max_ts_collected
            else:
                break

        for line in data:
            line["t"] = line["t"] // 1000

        return data

    def load_from_file(self, path, dt_1, dt_2):
        data = []
        ts_1, ts_2 = dt_to_ts(dt_1), dt_to_ts(dt_2)
        with open(path) as f:
            csv = f.readlines()
            fields = csv.pop(0).strip().split(",")
            reader = DictReader(csv, fields, quoting=QUOTE_NONNUMERIC)
            for row in reader:
                row["t"] = int(row["t"])
                if ts_1 <= row["t"] <= ts_2:
                    data.append(row)
        return data

    def load(self, sids, dt_1, dt_2):
        all_data = []

        for sid in list(sids):
            exchange, ticker = sid.split("_", 1)
            ticker = ticker.split("-")[0]

            if self.offline:
                # Фьючерсы из ib
                if sid.count("_") > 1:
                    path = os.path.join(self.path, "ib")
                    path = f"{path}/{exchange}/{sid}-trades.csv"
                    data = self.load_from_file(path, dt_1, dt_2)
                # Акции из полигона
                else:
                    path = os.path.join(self.path, "polygon")
                    path = f"{path}/{ticker}.csv"
                    data = self.load_from_file(path, dt_1, dt_2)
            else:
                data = self.load_from_api(ticker, dt_1, dt_2)

            if not data:
                log.error(f"No data for {sid}")
                continue

            data = sorted(data, key=lambda d: d["t"])

            prev_t = None
            payload = {}
            for line in data:
                # skip duplicate
                if line["t"] == prev_t:
                    continue

                # Заполняются небольшие пробелы в данных
                while prev_t and (60 < line["t"] - prev_t < 3600):
                    # добавить интервалы, пока не догоним line["t"]
                    prev_t += 60
                    payload = {
                        "dt": ts_to_dt(prev_t),
                        "o": line["c"],
                        "h": line["c"],
                        "l": line["c"],
                        "c": line["c"],
                        "v": 0,
                        "sid": sid,
                    }
                    all_data.append((prev_t, sid, payload))

                payload = {
                    "dt": ts_to_dt(line["t"]),
                    "o": line["o"],
                    "h": line["h"],
                    "l": line["l"],
                    "c": line["c"],
                    "v": line["v"],
                    "sid": sid,
                }
                all_data.append((line["t"], sid, payload))

                prev_t = line["t"]

        log.info(f"{dt_1}, {dt_2}, {len(all_data)}")

        return sorted(all_data)
