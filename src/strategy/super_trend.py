import json
import math
import sys
import numpy as np
import pandas as pd
import talib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from strategy import BaseStrategy, Signal
from util import trades_to_ohlc, interval_dt


class SuperTrend(BaseStrategy):
    intraday_only = False
    arr_lo = []
    arr_hi = []

    def __init__(self, **params):
        super().__init__()

        self.historical_short = []
        self.historical_last_ts = None

        self.length = params.pop("length")
        self.interval_size = 60 * 60
        self.indicator = {}

        self.atr_timeperiod = 10
        self.width_factor = 3

        self.update_id = None

        self.indicator_data = []

    def __str__(self):
        return f"<SuperTrend length={self.length}>"

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
                {"price": last_known_interval["open"], "size": "1"},
                {"price": last_known_interval["high"], "size": "1"},
                {"price": last_known_interval["low"], "size": "1"},
                {"price": last_known_interval["close"], "size": "1"},
            ]

        dt = interval_dt(trade) + timedelta(minutes=30)
        ts_q = math.ceil(dt.timestamp()) // self.interval_size
        # ts_q = round(trade["timestamp"] / (1000 * self.interval_size))
        # ts_q = trade["timestamp"] // (1000 * self.interval_size)

        ts_r = int(ts_q * 1000 * self.interval_size)
        trades_by_interval[ts_r].append(trade)

        ohlc_by_interval = list(map(trades_to_ohlc, trades_by_interval.items()))

        self.add_to_historical(ohlc_by_interval)

    def add_to_historical(self, data):
        for interval_ohlc in data:
            ts = interval_ohlc["timestamp"]
            if self.historical_last_ts == ts:
                # заменить последний интервал
                self.historical_short[-1] = interval_ohlc
            else:
                # добавить новый интервал
                self.historical_short.append(interval_ohlc)
                self.historical_last_ts = ts

        # Пересчитывать len_lo и len_hi оптимальным образом
        if len(self.historical_short) > self.length:
            removed_historical = self.historical_short.pop(0)

        self.historical += data

    def update_indicator(self):
        # print("update_indicator", len(self.historical))

        md = pd.DataFrame(self.historical[-300:])
        md["timestamp"] = pd.to_datetime(md["timestamp"] / 1000, unit="s")
        md.set_index("timestamp", inplace=True)

        md["close"] = pd.to_numeric(md["close"], downcast="float")
        md["high"] = pd.to_numeric(md["high"], downcast="float")
        md["low"] = pd.to_numeric(md["low"], downcast="float")

        # md["tr"] = talib.TRANGE(md["high"], md["low"], md["close"])
        # md["atr"] = talib.MA(md["tr"], timeperiod=self.atr_timeperiod, matype=1)

        md["atr"] = talib.ATR(
            md["high"], md["low"], md["close"], timeperiod=self.atr_timeperiod
        )

        ################

        md["src"] = (md["high"] + md["low"]) / 2
        md["dn"] = md["src"] + md["atr"] * self.width_factor
        md["up"] = md["src"] - md["atr"] * self.width_factor

        md["trend"] = 1
        cur_trend = 1

        prev_close = None
        prev_up = None
        prev_dn = None
        for row in md.itertuples():
            if not prev_close:
                prev_close = row.close
                prev_up = row.up
                prev_dn = row.dn
                continue

            if prev_close > prev_up:
                md.at[row.Index, "up"] = max(row.up, prev_up)
                prev_up = max(row.up, prev_up)
            else:
                prev_up = row.up

            if prev_close < prev_dn:
                md.at[row.Index, "dn"] = min(row.dn, prev_dn)
                prev_dn = min(row.dn, prev_dn)
            else:
                prev_dn = row.dn

            if cur_trend < 0 and row.close > prev_dn:
                cur_trend = 1
            elif cur_trend > 0 and row.close < prev_up:
                cur_trend = -1
            md.at[row.Index, "trend"] = cur_trend

            prev_close = row.close

        md["sig_up"] = (md["trend"] > 0) & (md["trend"].shift(1) < 0)
        md["sig_dn"] = (md["trend"] < 0) & (md["trend"].shift(1) > 0)

        ######
        # Индикаторы
        last_row = md.tail(1).reset_index()
        self.indicator = last_row.replace({np.nan: None}).to_dict(orient="records")[0]
        self.indicator["timestamp"] = self.indicator["timestamp"].to_pydatetime()

        if (
            self.indicator_data
            and self.indicator_data[-1]["timestamp"] == self.indicator["timestamp"]
        ):
            self.indicator_data.pop()
        self.indicator_data.append(self.indicator)

    def test_price(self, dt: datetime, price: Decimal) -> Signal:
        """
        Проверить сигнал стратегии после регистрации сделки.
        """
        signal = Signal.PASS
        if len(self.historical) < 1:
            return signal

        h_ts = int((dt + timedelta(minutes=30)).timestamp()) // (60 * 60)
        if not self.update_id or h_ts > self.update_id:
            # print("update_indicator", dt, h_ts)
            self.update_indicator()
            self.update_id = h_ts

        ##############

        if not self.indicator:
            return signal

        row = self.indicator

        # print(json.dumps(row, indent=2, default=str))

        if not row or not row["dn"] or not row["up"]:
            return signal

        if row["sig_up"]:
            signal = Signal.LONG

        elif row["sig_dn"]:
            signal = Signal.SHORT

        # if price > row["dn"]:
        #     signal = Signal.LONG
        #
        # elif price < row["up"]:
        #     signal = Signal.SHORT

        # if signal.value:
        #     txt = f"{dt:%Y-%m-%d %H:%M:%S} "
        #     txt += colored(f" Price: {price:0.4f} ", attrs=["reverse"])
        #     txt += f"Len: {len(self.historical)} • "
        #     txt += colored(f"{signal.value}", signal.color)
        #     print(txt)

        return signal
