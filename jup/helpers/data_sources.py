import pandas as pd

BASE_PATH = "~/projects/life/trrrading/data"


def resample_ohlc(md, rule):
    md = md.resample(rule).apply({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    })
    md.dropna(inplace=True)
    return md


def get_hist_data(ticker, start=None, end=None):

    ticker = ticker.replace(":", "")
    path = f"{BASE_PATH}/forex/DAT_ASCII_{ticker}_M1.csv"

    md = pd.read_csv(
        path,
        sep=";",
        names=["timestamp", "open", "high", "low", "close", "volume"]
    )
    md["timestamp"] = pd.to_datetime(md["timestamp"])
    md.set_index("timestamp", inplace=True)
    md.sort_index(inplace=True)

    if start:
        md.query(f"timestamp >= '{start}'", inplace=True)

    if end:
        md.query(f"timestamp <= '{end}'", inplace=True)

    return md


def get_exante_data(ticker, start=None, end=None):

    path = f"{BASE_PATH}/forex/live-{ticker}.E.FX-quotes-60.jsonl"

    md = pd.read_json(path, orient="records", lines=True)
    md = md.rename(
        columns={"open": "open", "high": "high", "low": "low", "close": "close"}
    )
    md = md.set_index("timestamp").sort_index()
    md.index = md.index.tz_localize("UTC")

    if start:
        md.query(f"timestamp >= '{start}'", inplace=True)

    if end:
        md.query(f"timestamp <= '{end}'", inplace=True)

    return md


###########################################
# https://pypi.org/project/investpy/
# import investpy
#
# df = investpy.get_stock_historical_data(stock='AAPL',
#                                         country='United States',
#                                         from_date='01/01/2010',
#                                         to_date='01/01/2020')
# print(df.head())
