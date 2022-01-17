import sys
import logging
import redis
import urllib3
import requests
import pandas_market_calendars as mcal
from time import sleep
from random import shuffle
from functools import cache
from collections import Counter
from termcolor import cprint
from datetime import datetime, timedelta, timezone
from os.path import abspath, join, dirname


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


log = logging.getLogger("loader")

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


HISTORY_URL = "https://localhost:5000/v1/api/iserver/marketdata/history"

instruments = [
    {
        "conid": 265598,
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "data_types": ["TRADES"],
    },
    {
        "conid": 461318791,
        "symbol": "MES",
        "exchange": "GLOBEX",
        "data_types": ["TRADES"],
    },
    {
        "conid": 461318792,
        "symbol": "MNQ",
        "exchange": "GLOBEX",
        "data_types": ["TRADES"],
    },
    {
        "conid": 131217639,
        "symbol": "BB",
        "exchange": "NYMEX",
        "data_types": ["TRADES"],
    },
    {
        "conid": 211651685,
        "symbol": "URA",
        "exchange": "ARCA",
        "data_types": ["TRADES"],
    },
    {
        "conid": 508109460,
        "symbol": "MNTS",
        "exchange": "NASDAQ",
        "data_types": ["TRADES"],
    },
]

exchange_schedule = {
    "NASDAQ": "NASDAQ",
    "NYMEX": "NYSE",
    "NYSE": "NYSE",
    "ARCA": "NYSE",
    "GLOBEX": "CME_Rate",
}


r = redis.Redis(host="localhost", port=6379, db=5)


def get_stats_for_hour(data, start):

    cnt = Counter()

    end = start + timedelta(hours=1)
    start_str = datetime.strftime(start, "%Y-%m-%d %H:%M:%S")
    end_str = datetime.strftime(end, "%Y-%m-%d %H:%M:%S")

    for val in data:
        line = val.decode()
        if start_str <= line[:19] < end_str:
            if "ERR" in line:
                cnt["error"] += 1
            elif "CLOSED" in line:
                cnt["closed"] += 1
            elif "FIX" in line or "LATE" in line:
                cnt["fix"] += 1
            else:
                cnt["ok"] += 1

    return cnt


def update_dash(instruments, csv_path):
    """
    Обновление CSV со статусами по часам.
    """
    end = datetime.utcnow()
    start = end - timedelta(hours=47)
    start = start.replace(minute=0, second=0, microsecond=0)

    dash_csv_data = "ticker,group,ok,closed,error,fix\n"

    for instrument in instruments:
        key = get_key(instrument)

        # Запросить данные для этого интервала
        data = r.zrangebyscore(key, dt_to_ts(start), 10 ** 10)

        # Сгруппировать данные по часам
        # Перебрать все часы от start до now
        for cur_hour in dt_range(start, end, timedelta(hours=1)):
            stats = get_stats_for_hour(data, cur_hour)
            dash_csv_data += (
                f"{key},{cur_hour},"
                f"{stats['ok']},{stats['closed']},"
                f"{stats['error']},{stats['fix']}\n"
            )

    with open(csv_path, "w") as f:
        f.write(dash_csv_data)


def dt_range(start, end, step=timedelta(minutes=1)):
    curr = start
    while curr <= end:
        yield curr
        curr += step


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts / 1000)


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_key(instrument):
    return "{symbol}.{exchange}:TRADES".format(**instrument)


def replace_data(instrument, line_str, ts):
    """
    Запись в базу с заменой старых данных.
    """
    key = get_key(instrument)
    cprint(f"{key}, {ts}, {line_str}", "white")
    r.zremrangebyscore(key, ts, ts)
    r.zadd(key, {line_str: ts})


@cache
def get_calendar_and_schedule(exchange):
    """
    Календарь и расписание для биржи.
    """
    calendar = mcal.get_calendar(exchange_schedule[exchange])

    # нужно покрыть вперед и назад все возможные выходные
    start = datetime.utcnow() - timedelta(days=5)
    end = datetime.utcnow() + timedelta(days=100)

    # TODO: убрать хардкодинг
    if exchange_schedule[exchange] in ["NYSE", "NASDAQ"]:
        schedule = calendar.schedule(start, end, start="pre", end="post")
    else:
        schedule = calendar.schedule(start, end)

    return calendar, schedule


@cache
def check_open_time(exchange, cur_interval):
    """
    Открыта ли эта биржа в указанный момент.
    """
    calendar, schedule = get_calendar_and_schedule(exchange)
    cur_interval_utc = cur_interval.replace(tzinfo=timezone.utc)
    return calendar.open_at_time(schedule, cur_interval_utc)


def load_intervals_from_ibkr(instrument, period, data_grid):
    # Запрос в IBKR
    try:
        data = {
            "conid": instrument["conid"],
            "period": f"{period}min",
            "bar": "1min",
            "outsideRth": True,
        }
        res = requests.get(HISTORY_URL, params=data, verify=False, timeout=3)
    except Exception as e:
        cprint(f"ERROR requests {e}", "red")
        raise e

    try:
        data = res.json()["data"]
        for interval in data:
            ts = interval["t"] // 1000
            dt = ts_to_dt(interval["t"])
            if ts in data_grid:
                interval["dt"] = dt
                line_str = "{dt} {o} {h} {l} {c} {v}".format(**interval)
                data_grid[ts]["new"] = line_str
                data_grid[ts]["t"] = interval["t"]
            else:
                pass
                # log.debug(f"Time is not in data_grid {ts} {dt}")
    except Exception as e:
        cprint(f"ERROR: {res.status_code} {res.text} {e}", "yellow")
        raise e

    return data_grid


def fill_gaps(instrument, data_grid):

    # # Последний успешно загруженный с биржи интервал
    # last_good_ts = dt_to_ts(datetime.utcnow())
    # for score, line in data_grid.items():
    #     data = line.get("old")
    #     if data and not ("ERROR" in data or "CLOSE" in data):
    #         last_good_ts = score * 1000

    # Последний интервал, когда биржа была открыта.
    # От него считается period.
    last_open_dt = datetime.utcnow() - timedelta(days=10)  # далеко в прошлом
    for score, line in data_grid.items():
        if line["is_it_open"]:
            last_open_dt = line["dt"]

    # Первый ключ плохих данных, которые нужно перезагружать
    first_bad_dt = None
    for score, line in data_grid.items():
        delta = (last_open_dt - line["dt"]).total_seconds() // 60
        if delta > 500:
            # Сшилком далеко в прошлое, не рассматриваем
            continue
        if delta < 0:
            # Интервал был после последнего закрытия, не рассматриваем
            break

        data = line.get("old")
        if not data or "ERROR" in data:
            first_bad_dt = line["dt"]
            break

    print()
    print("NOW UTC  ", datetime.utcnow().replace(microsecond=0))
    print("First bad", first_bad_dt)
    print("Last open", last_open_dt, dt_to_ts(last_open_dt))

    if first_bad_dt:
        # Хотим загрузить какие-то недогруженные данные
        period = int((last_open_dt - first_bad_dt).total_seconds() // 60) + 1
        cprint(f"GET IBKR DATA, period: {period}", "blue")
        try:
            data_grid = load_intervals_from_ibkr(instrument, period, data_grid)
        except Exception as e:
            log.error("load_intervals_from_ibkr")
            log.exception(e)

    # Сгенерить данные для закрытых интервалов
    for score, line in data_grid.items():
        if line.get("is_it_open") is False:
            if not line.get("old") or ("ERROR" in line.get("old")):
                line_str = "{dt} CLOSED".format(**line)
                data_grid[score]["new"] = line_str

    return data_grid


def update_instrument(interval_dt, instrument):

    # IBKR позволяет грузить данные только на 1000 интервалов назад,
    # но в них не входят интервалы закрытой биржи, поэтому делаю запас.
    cur_minute = datetime.utcnow().replace(second=0, microsecond=0)
    start = cur_minute - timedelta(days=3)

    # Пустая сетка интервалов с расписанием биржи
    data_grid = {}
    for cur_interval in dt_range(start, interval_dt):
        is_it_open = check_open_time(instrument["exchange"], cur_interval)
        data_grid[dt_to_ts(cur_interval)] = {
            "dt": cur_interval,
            "is_it_open": is_it_open,
        }

    # Интервалы в базе данных от start до конца
    data_in_db = r.zrangebyscore(get_key(instrument), dt_to_ts(start), 10 ** 10)

    # Положить интервалы из базы в сетку
    for line in data_in_db:
        line = line.decode()
        dt = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        ts = dt_to_ts(dt)
        if ts in data_grid:
            data_grid[ts]["old"] = line

    # Метод заполняет пробелы из IBKR или флагом "CLOSED"
    data_grid = fill_gaps(instrument, data_grid)

    # Найти различачающиеся данные и сохранить или вывести ошибку
    for score, line in data_grid.items():

        # Уже были данные
        if "old" in line:
            # Но теперь есть другие данные
            if "new" in line and line["new"] != line["old"]:
                replace_data(instrument, line["new"] + " FIX", score)

        # Данных не было
        else:
            if line.get("new"):
                # Если данные пришли не real-time, то ставлю флаг LATE
                late = " LATE" if line["dt"] < interval_dt else ""
                replace_data(instrument, line["new"] + late, score)
            else:
                log.debug("Данных всё нет и нет")

    current_interval_data = data_grid[dt_to_ts(interval_dt)]

    # Загрузка считается успешной, если появился new
    # или если есть old в статусе, не требующем изменения (не ошибка)
    done = bool(current_interval_data.get("new"))
    done = done or ("ERROR" not in current_interval_data.get("old", ""))
    return done


def loader(dt_start, instruments):
    """
    Грузить интервал, пока не загрузится или не наступит новый интервал.
    """
    timeout = 10  # максимальное время на загрузку одного инструмента
    sleep_time = 3

    # Какой интервал грузить
    cur_minute = dt_start.replace(second=0, microsecond=0)
    interval_dt = cur_minute - timedelta(minutes=1)

    # Перемешиваю, чтобы при залипании первого инструмента не застряли все
    shuffle(instruments)

    for instrument in instruments:
        while True:
            try:
                if update_instrument(interval_dt, instrument):
                    # Успешно загрузилось
                    break
            except Exception as e:
                cprint(f"ERROR load_interval {e}", "yellow")
                log.exception(e)

            dt = datetime.utcnow()

            # Если интервал так и не загрузился — записать ошибку

            if dt - dt_start > timedelta(seconds=timeout):
                cprint(f"ERROR интервал долго не грузится", "red")
                line_str = f"{interval_dt} ERROR: timeout"
                replace_data(instrument, line_str, dt_to_ts(interval_dt))

                # Прекращаем грузить инструмент
                break

            if dt.minute != dt_start.minute:
                cprint("ERROR пора грузить новый интервал", "red")
                line_str = f"{interval_dt} ERROR: too late"
                replace_data(instrument, line_str, dt_to_ts(interval_dt))

                # Прекращаем грузить данный интервал
                return

            # Перерыв после неудачной попытки
            sleep(sleep_time)


def main(instruments):
    base_dir = abspath(dirname(dirname(dirname(__file__))))
    csv_path = abspath(join(base_dir, "front/dash/dash.csv"))

    prev_dt = datetime(2000, 1, 1)
    while True:
        dt = datetime.utcnow()
        if dt.minute != prev_dt.minute and dt.second > 10:
            # Начать загрузку нового минутного интервала
            prev_dt = dt
            loader(dt, instruments)
            update_dash(instruments, csv_path)
            print()
            print("-------- конец цикла ---------", datetime.utcnow())
            print()
        else:
            sleep(1)


if __name__ == "__main__":
    dt = datetime.now()
    try:
        main(instruments)
    except KeyboardInterrupt:
        pass
    log.info(f"Done in {str(datetime.now() - dt)[:-7]}")
