"""
Получение исторических данных из IB, сохранение в виде файлов.
"""

import logging
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from time import sleep

import click
from pandas_market_calendars import MarketCalendar
from rich import print
from rich.logging import RichHandler

p = os.path.abspath("..")
if p not in sys.path:
    sys.path.insert(0, p)

from src.ibkr_api.client import IbContract, IBThread
from src.ibkr_api.ib_sync import IBSync

# Логгер для этого файла
log = logging.getLogger()

# log.setLevel(logging.INFO)

# coloredlogs.install(
#     "INFO", fmt="%(asctime).19s • %(levelname).1s • %(name)s • %(message)s"
# )

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="%X",
    handlers=[RichHandler(rich_tracebacks=True)],
)


BASE_DIR = "../data/ib"

ib_params = {
    # "host": "108.61.229.69",
    "host": "127.0.0.1",
    "clientId": 888,
    "timeout": 5,
    "port": 4002,
}


dt_format = click.DateTime(formats=["%Y-%m-%d"])


def get_calendar(name, open_time=None, close_time=None) -> MarketCalendar:
    name = name.replace("ARCA", "NYSE")
    name = name.replace("CME", "CMES")
    name = name.replace("CBOT", "CMES")
    name = name.replace("NYMEX", "CMES")
    return MarketCalendar.factory(name, open_time, close_time)  # type: ignore


def get_exchange_schedule(exchange, dt_start, dt_end):
    """
    Возвращает рабочие интервалы биржи по дням.
    Предполагается, что в питоне dict сохраняет порядок ключей.
    """
    market_calendar = get_calendar(exchange)
    schedule = market_calendar.schedule(dt_start, dt_end)
    res = {}
    for key, t in sorted(schedule.T.to_dict("list").items()):
        day = key.to_pydatetime().date()  # type: ignore
        res[day] = {
            "t0": t[0].to_pydatetime(),
            "t1": t[1].to_pydatetime(),
        }
    return res


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def get_last_interval_dt(f_path) -> datetime:
    """
    Вытаскивает timestamp из последней строки файла.
    """
    with open(f_path, "rb") as f:
        try:  # catch OSError in case of a one line file
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b"\n":
                f.seek(-2, os.SEEK_CUR)
        except OSError:
            f.seek(0)
        last_line = f.readline().decode()
        last_ts = int(last_line.split(",")[0])
        last_dt = datetime.utcfromtimestamp(last_ts)
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return last_dt


class IBSyncData(IBSync):
    pass


def get_market_data(ib: IBSync, symbol, data_type, dt_start, dt_end, force):

    symbol, exchange = str(symbol).upper().split(".")

    # Абстрактное описание контракта, не включающее дату экспирации
    base_contract = IbContract(symbol, secType="FUT", exchange=exchange)
    base_contract.includeExpired = True

    # Получение списка контрактов с разными датами
    details = ib.get_contract_details(base_contract)

    # Сортировка по дате экспирации (или типа того)
    details = [(c.contract.lastTradeDateOrContractMonth, c) for c in details]

    yesterday = datetime.now(tz=timezone.utc).date() - timedelta(days=1)

    for _, cd in sorted(details):
        contract = cd.contract
        exp_date_str = cd.realExpirationDate

        # Распарсить дату экспирации, вычесть полгода
        # Сделать поправку на first_day и dt_start

        exp_date = datetime.strptime(exp_date_str, "%Y%m%d").date()
        dt_1 = exp_date - timedelta(days=180)
        dt_1 = max(dt_1, dt_start)

        # Пропустить, если полученный dt_1 больше now
        if dt_1 > yesterday:
            log.info(f"Skip {contract.localSymbol}")
            continue

        # Получить первый день контракта
        ts = ib.get_head_timestamp(contract)
        first_day = datetime.utcfromtimestamp(int(ts)).date()

        # Последние две недели обычно можно не грузить
        exp_date = exp_date - timedelta(weeks=2)

        dt_1 = max(dt_1, first_day)
        dt_2 = min(exp_date, yesterday)

        if dt_1 >= dt_2:
            continue

        get_one_contract(ib, contract, data_type, dt_1, dt_2, force)


def get_one_contract(ib: IBSync, contract, data_type, dt_start, dt_end, force):

    # Разные заголовки и переменные для разных типов данных
    if data_type == "TRADES":
        header = "t,o,h,l,c,vw,v,n\n"
        row_tmpl = "{date},{open},{high},{low},{close},{wap},{volume},{barCount}\n"
    elif data_type == "BID_ASK":
        header = "t,av_bid,max_ask,min_bid,av_ask\n"
        row_tmpl = "{date},{open},{high},{low},{close}\n"
    elif data_type == "MIDPOINT":
        header = "t,o,h,l,c\n"
        row_tmpl = "{date},{open},{high},{low},{close}\n"
    else:
        log.error(f"Unknown data_type: {data_type}")
        return

    sid = ib.sid_for_contract(contract)
    exchange = sid.split("_", 1)[0]

    # Что грузить, summary
    log.info(f"{sid}, load: [{dt_start}, {dt_end}], {data_type}")

    # Создание имени файла и пути по шаблону
    f_name = f"{sid}-{data_type.lower()}.csv"
    f_path = os.path.abspath(f"{BASE_DIR}/{exchange}/{f_name}")


    # Проверить наличие файла и добыть последний сохраненный интервал
    valid_file_with_data = False
    last_interval_dt = (datetime.min).replace(tzinfo=timezone.utc)
    if os.path.exists(f_path):
        log.info(f"File exists:  {f_path}")
        if force:
            # Удаление старого файла
            os.remove(f_path)
            log.info(f"File removed: {f_path}")
        else:
            # Взять из файла последний интервал, для которого есть данные
            try:
                valid_file_with_data = True
                last_interval_dt = get_last_interval_dt(f_path)
                log.info(f"Last existing interval for {sid}: {last_interval_dt}")
            except:
                log.error(f"Can't get last existing interval for {sid}")
                return

    # Если файла не было, создать новый файл с заголовком
    if not valid_file_with_data:
        with open(f_path, "w") as f:
            f.write(header)
            log.info(f"File created: {f_path}")

    # Добыть расписание биржи в нужные дни
    schedule = get_exchange_schedule(exchange, dt_start, dt_end)

    # Загрузить каждый рабочий день, дописать в файл
    for day, day_schedule in schedule.items():
        t0 = day_schedule["t0"]
        t1 = day_schedule["t1"]
        t0_ts = dt_to_ts(t0)

        if t1 <= last_interval_dt:
            log.info(f"SKIP day: {day}")
            continue

        # Форматирование даты для запроса к IB
        end_dt = t1.strftime("%Y%m%d-%H:%M:%S")

        # Запрос к IB
        day_data = ib.get_historical_data(
            contract=contract,
            end_dt=end_dt,
            duration="86400 S",
            bar_size="1 min",
            data_type=data_type,
            use_rth=0,
        )

        # Если в работе биржи есть перерывы, то в 86400 рабочих секунд
        # войдут и предыдущие дни, поэтому нужно отрезать всё до t0.
        day_data_clean = []
        for line in day_data:
            if int(line.date) >= t0_ts and line.close > 0:
                day_data_clean.append(line)

        # Добавить данные в файл
        txt = ""
        sum_vol = 0
        for line in day_data_clean:
            # print( datetime.fromtimestamp(int(line.date)), line )
            sum_vol += int(line.barCount)
            # FIXME: Форматирование данных (разное для разных типов данных)
            # ibapi.utils.floatMaxString(self.open),
            # ibapi.utils.floatMaxString(self.high),
            # ibapi.utils.floatMaxString(self.low),
            # ibapi.utils.floatMaxString(self.close),
            # ibapi.utils.decimalMaxString(self.volume),
            # ibapi.utils.decimalMaxString(self.wap),  - округлить до 4 знаков
            # ibapi.utils.intMaxString(self.barCount)
            txt += row_tmpl.format(**line.__dict__)

        log.info(f"Loaded: {day}, from: '{t0}', to: '{t1}', sum_vol: {sum_vol}")

        # Дописать данные в файл
        with open(f_path, "a") as f:
            f.write(txt)


@click.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option("--start", type=dt_format)
@click.option("--end", type=dt_format)
@click.option("--force", is_flag=True)
@click.option("--midpoint/--no-midpoint", is_flag=True)
@click.option("--bidask/--no-bidask", is_flag=True)
@click.option("--trades/--no-trades", is_flag=True, default=True)
def main(**kwargs):
    """
    python get_ib_market_data.py mes.cme --start 2020-12-20

    Examples:
        mes.cme
        mym.cbot
        hg.nymex
        aapl.nasdaq
        fcx.nyse
        copx.arca
    """
    dt = datetime.now()

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

    symbols = list(kwargs.get("symbols", []))

    app = IBSyncData()

    print(ib_params)

    try:
        app.connect(ib_params["host"], ib_params["port"], 900)

        # Endless message loop
        thread = IBThread(app)
        thread.start()

        # Wain for connection
        while True:
            if isinstance(app.nextValidOrderId, int):
                log.info(f"IB Connected")
                break
            sleep(0.5)

        for symbol in symbols:
            for data_type in data_types:
                get_market_data(app, symbol, data_type, dt_start, dt_end, force)

    except (KeyboardInterrupt, SystemExit):
        print()
        log.info("Stop\n")

    finally:
        app.disconnect()

    print(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
