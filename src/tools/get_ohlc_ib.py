"""
Получение исторических данных из IB, сохранение в виде файлов.
"""

import os
import random
import click
import pytz
import pandas as pd
import requests
import socket
import pandas_market_calendars as mcal
from os.path import abspath, dirname
from datetime import datetime, timezone, timedelta
from ib_insync import *
from pathlib import Path
from termcolor import cprint
from contextlib import closing


BASE_DIR = abspath(dirname(__file__) + "/../../data")

BID_ASK_COLUMNS_MAP = {
    "open": "av_bid",
    "high": "max_ask",
    "low": "min_bid",
    "close": "av_ask",
}

dt_format = click.DateTime(formats=["%Y-%m-%d"])

# Можно пробросить порт с удаленной машины:
# ssh -L 4001:127.0.0.1:4001 root@51.15.62.103

port_tws = 7497
port_gw = 4001

ib_params = {
    "host": "127.0.0.1",
    "clientId": random.randint(20, 99),
    "timeout": 5,
}

ib = IB()


def get_file_name(exchange, symbol, data_type, date):
    data_type = data_type.replace("_", "")
    return f"{BASE_DIR}/{exchange}/{symbol}/{data_type}/{date:%Y-%m-%d}.txt"


def get_splits_file_name(exchange, symbol):
    return f"{BASE_DIR}/{exchange}/{symbol}/splits.txt"


def get_first_day(contract):
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


def get_data(contract, day, data_type, timeframe="1 min"):
    day_utc = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_utc = day_utc + timedelta(hours=27)  # +27H — чтобы закрыть весь торговый день

    # day_end = f"{day:%Y%m%d 23:59:59} UTC"
    # print(day, " | ", day_end, " | ", day_utc)

    if contract.exchange in ["NYMEX", "GLOBEX", "ECBOT"]:
        duration = "2 D"
    else:
        duration = "1 D"

    bars = ib.reqHistoricalData(
        contract,
        endDateTime=day_utc,
        durationStr=duration,
        barSizeSetting=timeframe,
        whatToShow=data_type,
        useRTH=False,
        formatDate=2,
        timeout=120,
    )
    if len(bars) == 0:
        raise ValueError("Empty response")

    if contract.exchange in ["NYMEX", "GLOBEX", "ECBOT"]:
        ex_tz = pytz.timezone('America/New_York')
        t = datetime.combine(day, datetime.min.time()).astimezone(ex_tz)
        t0 = t - timedelta(days=1) + timedelta(hours=14, minutes=30)
        t1 = t + timedelta(hours=14, minutes=30)
        only_one_day = []
        for bar in bars:
            dt = bar.date
            if t0 <= dt < t1:
                only_one_day.append(bar)
        bars = only_one_day
        # print(util.df(bars))

    return util.df(bars)


def get_splits(ticker):
    ticker = ticker.split(".")[0]
    params = "interval=3mo&events=split&period1=1400000000&period2=1800000000"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{params}"
    res = requests.get(url, headers={"User-Agent": "Godzilla"}, timeout=5)
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


def download_and_save(contract, data_types=None, start=None, end=None, force=False):
    data_types = data_types or ["BID_ASK", "TRADES"]

    symbol = contract.symbol
    exchange = contract.primaryExchange or contract.exchange

    ticker = f"{symbol}.{exchange}"

    if contract.secType == "FUT":
        contract.includeExpired = True
        contracts = ib.reqContractDetails(contract)
        contract_exp_dates = [c.contract.lastTradeDateOrContractMonth for c in contracts]
        contract_exp_dates = sorted(contract_exp_dates)
        contract.lastTradeDateOrContractMonth = contract_exp_dates[0]
    else:
        contract_exp_dates = None

    try:
        first_day = get_first_day(contract)
    except ValueError:
        cprint(f"Can't get the first day for {symbol}", "red")
        return False

    start = start or datetime(2021, 1, 1, tzinfo=timezone.utc).date()

    yesterday = datetime.now(tz=timezone.utc).date() - timedelta(days=1)
    end = min(end or yesterday, yesterday)

    start = max(start, first_day)

    cprint(f"{ticker}, fd: {first_day}, [{start}, {end}], {data_types}", "blue")

    cal_exchange = exchange
    cal_exchange = cal_exchange.replace("ARCA", "NYSE")
    cal_exchange = cal_exchange.replace("NYMEX", "CMES")
    cal_exchange = cal_exchange.replace("GLOBEX", "CMES")
    cal_exchange = cal_exchange.replace("ECBOT", "CMES")

    cal = mcal.get_calendar(cal_exchange).schedule(start, end)

    splits = None
    if contract.secType == "STK":
        try:
            splits = get_splits(ticker)
        except ValueError:
            cprint(f"Can't get splits for {symbol}", "red")

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

        # d0, d1 = t0.date(), t1.date()
        middle_date = t0 + (t1 - t0) / 2
        # assert d0 == d1
        # assert d0 < datetime.now(tz=timezone.utc).date()

        for data_type in data_types:
            dt = datetime.now()
            f_name = get_file_name(exchange, symbol, data_type, day)

            # вдруг такой файл уже есть
            if Path(f_name).is_file() and not force:
                # cprint(f"SKIP: {f_name}", "yellow")
                continue

            # Для фьючерсов тут уточняется, какой
            # именно контракт получать для этой даты.
            if contract.secType == "FUT":
                exp_date = None
                for ced in contract_exp_dates:
                    if ced >= middle_date.strftime("%Y%m%d"):
                        exp_date = ced
                        break
                contract.lastTradeDateOrContractMonth = exp_date

            # Получить данные за день
            try:
                df = get_data(contract, day=middle_date, data_type=data_type)
            except ValueError:
                cprint(f"Empty response: {symbol}, {day}, {data_type}", "red")
                continue
            except ConnectionError as e:
                cprint(f"ConnectionError: {symbol}, {day}, {data_type}", "red")
                cprint(e, "red")
                continue

            if type(df).__name__ == "NoneType" or df.empty:
                cprint(f"No data: {middle_date}, {data_type}", "blue")
                continue

            # Пометить рабочие часы
            if contract.secType == "STK":
                df["rth"] = (df["date"] >= t0) & (df["date"] < t1)
                df["rth"] = df["rth"].astype(int)
            else:
                df["rth"] = 1

            df["date"] = df["date"].dt.tz_localize(None)
            df = df.set_index("date")

            # Убрать нулевые объемы
            # df = df.loc[df.volume != 0]

            # В режиме BID_ASK данные имеют другой смысл. Переименовать.
            if data_type == "BID_ASK":
                df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)
                # Убрать записи, где не было изменений.
                # Запись для начала основной сессии (RTH) сохраняется.
                # df = df.drop_duplicates(
                #     subset=["av_bid", "max_ask", "min_bid", "av_ask", "rth"],
                #     keep="first",
                # )

            # Создать директорию, если надо
            d_name = os.path.dirname(f_name)
            Path(d_name).mkdir(parents=True, exist_ok=True)

            df.to_csv(f_name, sep="\t")

            time = (datetime.now() - dt).total_seconds()
            cprint(f"DONE: {f_name}, {len(df)} lines, {time:0.2f} s", "green")


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


@click.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option("--start", type=dt_format)
@click.option("--end", type=dt_format)
@click.option("--force", is_flag=True)
@click.option("--midpoint", is_flag=True)
@click.option("--bidask", is_flag=True, default=True)
@click.option("--trades", is_flag=True, default=True)
def main(**kwargs):
    """
    python get_ohlc_ib.py mes.globex --start 2020-12-20

    Examples:
    mes.globex
    mym.ecbot
    hg.nymex
    aapl.nasdaq
    fcx.nyse
    copx.arca
    """
    dt = datetime.now()

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(1)
        if sock.connect_ex((ib_params["host"], port_tws)) == 0:
            ib_params["port"] = port_tws
        else:
            ib_params["port"] = port_gw

    print(f"Using port {ib_params['port']}")

    ib.connect(**ib_params)

    last_week = datetime.now() - timedelta(7)
    dt_start = (kwargs.get("start") or last_week).date()
    dt_end = (kwargs.get("end") or datetime.now()).date()
    force = kwargs.get("force", False)

    data_types = []
    if kwargs.get("midpoint"):
        data_types.append("MIDPOINT")
    if kwargs.get("bidask"):
        data_types.append("BID_ASK")
    if kwargs.get("trades"):
        data_types.append("TRADES")

    for stock in kwargs.get("symbols"):
        stock = stock.upper()
        if "." in stock:
            symbol, pe = stock.split(".")
        else:
            symbol = stock
            pe = "ARCA"

        if pe in ["GLOBEX", "ECBOT", "NYMEX"]:
            contract = Future(symbol, exchange=pe, currency="USD")
        else:
            contract = Stock(symbol, "SMART", "USD", primaryExchange=pe)

        download_and_save(contract, data_types, dt_start, dt_end, force)
        print()

    print(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
