import os
import pandas as pd
from datetime import timezone, datetime, timedelta
from io import StringIO
from settings import BASE_DIR


DATA_BASE_DIR = BASE_DIR / "src" / "history"

TRADES_NUM_COL = ["open", "high", "low", "close", "volume", "average", "barCount"]
BIDASK_NUM_COL = ["av_bid", "max_ask", "min_bid", "av_ask"]


def get_file_name(exchange, symbol, data_type, date):
    data_type = data_type.replace("_", "")
    return f"{DATA_BASE_DIR}/{exchange}/{symbol}/{data_type}/{date:%Y-%m-%d}.txt"


def get_splits_file_name(exchange, symbol):
    return f"{DATA_BASE_DIR}/{exchange}/{symbol}/splits.txt"


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def load_as_df(ticker, data_type, start=None, end=None):
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

    # Добавляю фейковые записи в минутных промежутках
    # (только в основную сессию)
    # OHLC и average равны последнему известному close
    if data_type == "TRADES":
        df1 = df.resample('1T').pad()

        df1["volume"] = df["volume"]
        df1["volume"].fillna("0", inplace=True)

        df1["barCount"] = df["barCount"]
        df1["barCount"].fillna("0", inplace=True)

        df1.loc[df1['volume'] == "0", ["open", "high", "low", "average"]] = df1["close"]

        df1 = df1[(df1["barCount"] != "0") | (df1["rth"] == "1")]
        df = df1

    # Добавляю фейковые записи в минутрых промежутках
    if data_type == "BIDASK":
        df = df.resample('1T').pad()

    # Добавить колонку в начало df
    df.insert(loc=0, column="ticker", value=ticker)
    df.insert(loc=1, column="data_type", value=data_type)

    if data_type == "BIDASK":
        df.drop(["volume", "average", "barCount"], axis=1, inplace=True)
        df[BIDASK_NUM_COL] = df[BIDASK_NUM_COL].apply(pd.to_numeric)

    if data_type == "TRADES":
        df[TRADES_NUM_COL] = df[TRADES_NUM_COL].apply(pd.to_numeric)

    return df


def load_many(tickers, data_types, start, end=None):
    dfs = []
    for ticker in tickers:
        for data_type in data_types:
            dfs.append(load_as_df(ticker, data_type, start=start, end=end))
    df = pd.concat(dfs)
    df.sort_index(inplace=True)
    return df
