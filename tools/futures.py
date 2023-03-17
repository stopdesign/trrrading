"""
Получение исторических данных из IB, сохранение в виде файлов.
"""

import json
import os
import random
import click
import pytz
import socket
import pandas_market_calendars as mcal
from os.path import abspath, dirname
from datetime import datetime, timezone, timedelta, time
from ib_insync import *
from pathlib import Path
from termcolor import cprint
from contextlib import closing
from bisect import bisect
import dataclasses


BASE_DIR = abspath(dirname(__file__) + "/../data")

BID_ASK_COLUMNS_MAP = {
    "open": "av_bid",
    "high": "max_ask",
    "low": "min_bid",
    "close": "av_ask",
}

dt_format = click.DateTime(formats=["%Y-%m-%d"])

# Можно пробросить порт с удаленной машины:
# ssh -L 4001:127.0.0.1:4001 root@51.15.62.103

# Ports by default:
# 7497 TWS paper
# 7496 TWS real
# 4002 IB Gateway paper
# 4001 IB Gateway real

port_tws = 7496
port_gw = 4001

ib_params = {
    "host": "127.0.0.1",
    "clientId": random.randint(20, 99),
    "timeout": 5,
}

ib = IB()


def get_file_name(exchange, symbol, data_type, date, exp_day):
    data_type = data_type.replace("_", "")
    return f"{BASE_DIR}/{exchange}/{symbol}/{exp_day}/{data_type}/{date:%Y-%m-%d}.txt"


def get_first_day(contract):
    date = None
    for i in range(10):
        date = ib.reqHeadTimeStamp(
            contract, whatToShow="MIDPOINT", useRTH=False, formatDate=2,
        )
        if date:
            break
    if not date:
        raise ValueError("Empty response")
    return date.date()


def get_data(contract, day, data_type, timeframe="1 min"):
    day_utc = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_utc = day_utc + timedelta(hours=35)  # +27H — чтобы закрыть весь торговый день

    # day_end = f"{day:%Y%m%d 23:59:59} UTC"
    # print(day, " | ", day_end, " | ", day_utc)

    if contract.exchange in ["NYMEX", "GLOBEX", "CBOT", "COMEX"]:
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

    # print(util.df(bars))
    # util.df(bars).to_csv("1.df", sep="\t")

    # ТУТ ПРОИСХОДИТ КАКОЕ-ТО ГОВНО, КОТОРОЕ СРЕЗАЕТ КОРОТКИЕ ДНИ
    # 2021-01-18 CBOT/ZW
    # Похоже, в такие дни нет сделок, если считать по UTC

    if contract.exchange in ["NYMEX", "GLOBEX", "CBOT", "COMEX"]:
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


def get_contract_day_data(contract, day, data_type, force):
    """
    Получить данные за день
    """

    dt = datetime.now()

    symbol = contract.symbol
    exp_day = contract.lastTradeDateOrContractMonth
    exchange = contract.primaryExchange or contract.exchange

    f_name = get_file_name(exchange, symbol, data_type, day, exp_day)

    # вдруг такой файл уже есть
    if Path(f_name).is_file() and not force:
        cprint(f"SKIP: {f_name}", "yellow")
        return

    try:
        df = get_data(contract, day=day, data_type=data_type)
    except ValueError:
        cprint(f"Empty response: {symbol}, {day}, {data_type}", "red")
        return
    except ConnectionError as e:
        cprint(f"ConnectionError: {symbol}, {day}, {data_type}", "red")
        cprint(e, "red")
        return

    if type(df).__name__ == "NoneType" or df.empty:
        cprint(f"No data: {day}, {data_type}", "blue")
        return

    # Пометить рабочие часы
    df["rth"] = 1

    df["date"] = df["date"].dt.tz_localize(None)
    df = df.set_index("date")

    # Убрать нулевые объемы в моменты, когда биржа закрыта
    # df = df.loc[df.volume != 0]

    # В режиме BID_ASK данные имеют другой смысл. Переименовать.
    if data_type == "BID_ASK":
        df.rename(columns=BID_ASK_COLUMNS_MAP, inplace=True)

    # Создать директорию, если надо
    d_name = os.path.dirname(f_name)
    Path(d_name).mkdir(parents=True, exist_ok=True)

    df.to_csv(f_name, sep="\t")

    vol_sum = int(df["volume"].sum())

    load_time = (datetime.now() - dt).total_seconds()
    cprint(f"DONE: {f_name}, lines: {len(df)}, vol_sum: {vol_sum}, {load_time:0.2f} s", "green")


def download_and_save(contract, data_types=None, start=None, end=None, force=False):
    data_types = data_types or ["BID_ASK", "TRADES"]

    symbol = contract.symbol

    exchange = contract.primaryExchange or contract.exchange

    ticker = f"{symbol}.{exchange}"

    if contract.secType == "FUT":
        contract.includeExpired = True
        contracts = ib.reqContractDetails(contract)

        # print(Contract(conId=11160683))   #contracts[0]
        # print(ib.reqContractDetails(Contract(conId=11160683)))   #contracts[0]
        # res = get_data(Contract(conId=11160683), start, "MIDPRICE")
        # print(res)

        exp_dates = [c.contract.lastTradeDateOrContractMonth for c in contracts]
        exp_dates = sorted(exp_dates)
        contract.lastTradeDateOrContractMonth = exp_dates[0]
    else:
        exp_dates = None

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
    cal_exchange = cal_exchange.replace("CBOT", "CMES")
    cal_exchange = cal_exchange.replace("COMEX", "CMES")

    calendar = mcal.get_calendar(cal_exchange)

    schedule = calendar.schedule(start, end)

    for day, t in sorted(schedule.T.to_dict("list").items()):
        t0 = t[0].to_pydatetime().replace(tzinfo=timezone.utc)
        t1 = t[1].to_pydatetime().replace(tzinfo=timezone.utc)

        # d0, d1 = t0.date(), t1.date()
        middle_date = t0 + (t1 - t0) / 2
        # assert d0 == d1
        # assert d0 < datetime.now(tz=timezone.utc).date()

        for data_type in data_types:

            # Разные даты для квартальных и месячных контрактов
            exp_date_limit = middle_date
            if middle_date.day < 28:
                exp_date_limit = middle_date + timedelta(days=1)

            # Current contract index
            con_idx = bisect(exp_dates, exp_date_limit.strftime("%Y%m%d"))

            # Даты контрактов от Current до Current + N
            exp_dates_to_load = exp_dates[con_idx:con_idx+4]

            # Загрузка
            for exp_date in exp_dates_to_load:
                contract.lastTradeDateOrContractMonth = exp_date
                get_contract_day_data(contract, middle_date, data_type, force)

            print()


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


@click.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option("--start", type=dt_format)
@click.option("--end", type=dt_format)
@click.option("--force", is_flag=True, default=False)
@click.option("--midpoint/--no-midpoint", is_flag=True, default=False)
@click.option("--bidask/--no-bidask", is_flag=True, default=False)
@click.option("--trades/--no-trades", is_flag=True, default=True)
def main(**kwargs):
    """
    python get_ohlc_ib.py mes.globex --start 2020-12-20

    Examples:
    mes.globex
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

    for stock in list(kwargs.get("symbols", [])):
        stock = stock.upper()
        if "." in stock:
            symbol, pe = stock.split(".")
        else:
            symbol = stock
            pe = "ARCA"

        if pe in ["NYMEX", "GLOBEX", "CBOT", "COMEX"]:
            contract = Future(symbol, exchange=pe, currency="USD")
        else:
            contract = Stock(symbol, "SMART", "USD", primaryExchange=pe)

        download_and_save(contract, data_types, dt_start, dt_end, force)
        print()

    print(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
