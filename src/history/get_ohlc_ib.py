"""
Получение исторических данных из IB.

1. Узнать дату создания данной бумаги.

2. Получить расписание биржи, на которой оно торгуется.

3. Загрузить сплиты.

4. Загрузить минутные данные по дням.

"""
import json
import os
from collections import Counter
from io import StringIO
import pandas as pd
import requests
import pandas_market_calendars as mcal
from datetime import datetime, timezone, timedelta
from ib_insync import *
from pathlib import Path
from time import sleep
from termcolor import cprint

from strategy import ChannelBreakout3, Signal

BASE_DIR = "."

BID_ASK_COLUMNS_MAP = {
    "open": "av_bid",
    "high": "max_ask",
    "low": "min_bid",
    "close": "av_ask",
}

ib_params = {
    "host": "127.0.0.1",
    "port": 4001,  # 7497
    "clientId": 0,
    "timeout": 10,
}

ib = IB()
ib.connect(**ib_params)


def get_file_name(exchange, symbol, data_type, date):
    data_type = data_type.replace("_", "")
    return f"{BASE_DIR}/{exchange}/{symbol}/{data_type}/{date:%Y-%m-%d}.txt"


def get_splits_file_name(exchange, symbol):
    return f"{BASE_DIR}/{exchange}/{symbol}/splits.txt"


def get_first_day(symbol):
    contract = Stock(symbol, "SMART", "USD", primaryExchange="ARCA")
    date = None
    for i in range(10):
        date = ib.reqHeadTimeStamp(
            contract, whatToShow="TRADES", useRTH=False, formatDate=2,
        )
        if date:
            break
    if not date:
        raise ValueError("Empty response")
    return date.date()


def get_data(symbol, day, data_type="TRADES", timeframe="1 min"):
    contract = Stock(symbol, "SMART", "USD", primaryExchange="ARCA")
    day_utc = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_utc = day_utc + timedelta(hours=27)  # +27H — чтобы закрыть весь торговый день
    bars = []
    for i in range(10):
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=day_utc,
            durationStr="1 D",
            barSizeSetting=timeframe,
            whatToShow=data_type,
            useRTH=False,
            formatDate=2,
            timeout=120,
        )
        if len(bars):
            break
    if len(bars) == 0:
        raise ValueError("Empty response")
    return util.df(bars)


def get_splits(ticker):
    ticker = ticker.split(".")[0]
    params = "interval=3mo&events=split&period1=1400000000&period2=1800000000"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{params}"
    res = requests.get(url, headers={"User-Agent": "Godzilla"})
    splits = None
    for i in range(10):
        try:
            splits = res.json()["chart"]["result"][0].get("events", {}).get("splits", {})
            splits = sorted(splits.values(), key=lambda x: x["date"], reverse=True)
            break
        except Exception as e:
            cprint(f"Failed finance.yahoo.com request: {e}", "red")
    if splits is None:
        raise ValueError("Empty response")
    return splits


def download_and_save(ticker="COPX.ARCA", start=None, data_types=None):

    data_types = data_types or ["BID_ASK", "TRADES"]

    symbol, exchange = ticker.split(".")

    try:
        first_day = get_first_day(symbol)
    except ValueError:
        cprint(f"Can't get the first day for {symbol}", "red")
        return False

    start = start or datetime(2021, 1, 1, tzinfo=timezone.utc).date()
    end = datetime.now(tz=timezone.utc).date() - timedelta(days=1)

    start = max(start, first_day)

    cprint(f"{ticker}, fd: {first_day}, [{start}, {end}], {data_types}", "blue")

    cal_exchange = exchange.replace("ARCA", "NYSE")
    cal = mcal.get_calendar(cal_exchange).schedule(start, end)

    try:
        splits = get_splits(ticker)
    except ValueError:
        cprint(f"Can't get splits for {symbol}", "red")
        return False

    if splits:
        df = pd.DataFrame.from_records(splits)
        df["date"] = pd.to_datetime(df["date"], unit="s")
        df = df.set_index("date")
    else:
        df = pd.DataFrame(
            index=["date"], columns=["numerator", "denominator", "splitRatio"]
        )

    f_name = get_splits_file_name(exchange, symbol)
    d_name = os.path.dirname(f_name)
    Path(d_name).mkdir(parents=True, exist_ok=True)

    df.to_csv(f_name, sep="\t")

    for day, t in sorted(cal.T.to_dict("list").items()):
        t0 = t[0].to_pydatetime().replace(tzinfo=timezone.utc)
        t1 = t[1].to_pydatetime().replace(tzinfo=timezone.utc)

        d0, d1 = t0.date(), t1.date()
        assert d0 == d1
        # assert d0 < datetime.now(tz=timezone.utc).date()

        for data_type in data_types:
            dt = datetime.now()
            f_name = get_file_name(exchange, symbol, data_type, day)

            # вдруг такой файл уже есть
            if Path(f_name).is_file():
                cprint(f"SKIP: {f_name}", "yellow")
                continue

            # Получить данные за день
            try:
                df = get_data(symbol=symbol, day=d0, data_type=data_type)
            except ValueError:
                cprint(f"Empty response: {symbol}, {day}, {data_type}", "red")
                continue
            except ConnectionError as e:
                cprint(f"ConnectionError: {symbol}, {day}, {data_type}", "red")
                cprint(e, "red")
                continue

            # Пометить рабочие часы
            df["rth"] = (df["date"] >= t0) & (df["date"] < t1)
            df["rth"] = df["rth"].astype(int)

            df["date"] = df["date"].dt.tz_localize(None)
            df = df.set_index("date")

            # Убрать нулевые объемы
            df = df.loc[df.volume != 0]

            # В режиме BID_ASK данные имеют другой смысл. Переименовать.
            if data_type == "BID_ASK":
                df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)
                # Убрать записи, где не было изменений.
                # Запись для начала основной сессии (RTH) сохраняется.
                df = df.drop_duplicates(
                    subset=["av_bid", "max_ask", "min_bid", "av_ask", "rth"],
                    keep="first",
                )

            # Создать директорию, если надо
            d_name = os.path.dirname(f_name)
            Path(d_name).mkdir(parents=True, exist_ok=True)

            df.to_csv(f_name, sep="\t")

            time = (datetime.now() - dt).total_seconds()
            cprint(f"DONE: {f_name}, {len(df)} lines, {time:0.2f} s", "green")


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def load_as_df(ticker="COPX.ARCA", start=None, end=None, data_type="TRADES"):
    """
    Загрузка исторических данных из файловой системы.
    """
    symbol, exchange = ticker.split(".")

    if not end:
        end = datetime.now().astimezone(timezone.utc).date()

    # Загрузить нужные дни
    data = ""
    for date in daterange(start, end):
        path = get_file_name(exchange, symbol, data_type, date)
        if os.path.isfile(path):
            data += open(path).read()

    df = pd.read_csv(StringIO(data), sep="\t", index_col="date", dtype=str)
    df = df[df["rth"] != "rth"]  # убрать заголовочные строки
    df.index = pd.to_datetime(df.index, utc=False)
    df.sort_index(inplace=True)

    # Отфильтровать данные по времени
    df = df.loc[start:end]

    # print(len(df))
    # print(df.index)

    return df


def test_strat_speed(df):

    strategy = ChannelBreakout3(length=350)

    cur_state = Signal.PASS

    stat = Counter()

    # Convert some columns to numeric type
    ohlc = ["open", "high", "low", "close"]
    df[ohlc] = df[ohlc].apply(pd.to_numeric)

    for row in df.itertuples():
        stat["bar"] += 1
        if row.rth == "1":
            stat["bar_rth"] += 1
            for price in [row.open, row.high, row.low, row.close]:
                signal = strategy.test_price(price)
                if signal.value and signal != cur_state:
                    cur_state = signal
                    stat["trade"] += 1
                    print(row.Index, signal)
                    break
            strategy.on_bar(row)

    print(json.dumps(stat, indent=2, default=str))


if __name__ == "__main__":
    dt = datetime.now()

    start_dt = datetime(2021, 7, 1, tzinfo=timezone.utc).date()
    download_and_save("URA.ARCA", start=start_dt)

    # start_dt = datetime(2021, 1, 1, tzinfo=timezone.utc).date()
    # df = load_as_df("COPX.ARCA", start=start_dt)
    # test_strat_speed(df)

    cprint(f"\nDone in {(datetime.now() - dt).total_seconds():0.2f} s", attrs=["bold"])
