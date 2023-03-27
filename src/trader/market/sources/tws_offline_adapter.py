import logging
import os
from csv import QUOTE_NONNUMERIC, DictReader
from datetime import datetime, timezone

from termcolor import cprint

from .base_source import BaseSource

log = logging.getLogger("tws_offline_adapter")


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class TwsOfflineAdapter(BaseSource):
    def __init__(self, path: str):
        self.path = path

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(offline=True)"

    def load_from_path(self, sid, dt_1, dt_2, path):
        data = []
        ts_1, ts_2 = dt_to_ts(dt_1), dt_to_ts(dt_2)
        exchange, symbol = sid.split("_", 1)
        with open(f"{path}/{exchange}/{sid}-trades.csv") as f:
            csv = f.readlines()
            fields = csv.pop(0).strip().split(",")
            reader = DictReader(csv, fields, quoting=QUOTE_NONNUMERIC)
            for row in reader:
                row["t"] = int(row["t"])
                if ts_1 <= row["t"] <= ts_2:
                    data.append(row)
        return data

    def load_from_file(self, symbol, dt_1, dt_2):
        """
        Здесь будут собираться данные по разным фьючерсным контрактам.
        """
        data = []
        path = os.path.abspath(self.path)
        data += self.load_from_path(symbol, dt_1, dt_2, path)
        return data

    def load(self, symbols, dt_1, dt_2):
        all_data = []

        for symbol in list(symbols):

            data = self.load_from_file(symbol, dt_1, dt_2)

            if not data:
                log.error(f"No data for {symbol}")
                continue

            data = sorted(data, key=lambda d: d['t'])

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
                    dt = ts_to_dt(prev_t)

                    # # Удаление всех данных за пределами RTH
                    # if self.schedule.is_rth(symbol, dt):
                    payload = payload.copy()
                    payload["dt"] = dt
                    payload["v"] = 0
                    all_data.append((prev_t, symbol, payload))

                dt = ts_to_dt(line["t"])

                # Удаление всех данных за пределами RTH
                # if self.schedule.is_rth(symbol, dt):
                payload = {
                    "dt": dt,
                    "o": line["o"],
                    "h": line["h"],
                    "l": line["l"],
                    "c": line["c"],
                    "v": line["v"],
                    "sid": symbol,
                }
                all_data.append((line["t"], symbol, payload))

                prev_t = line["t"]

        log.info(f"{dt_1}, {dt_2}, {len(all_data)}")

        return sorted(all_data)
