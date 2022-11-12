import logging
import os.path
import sys
from datetime import datetime, timedelta, timezone
from time import sleep

import click
import coloredlogs
import requests

log = logging.getLogger("polygon_loader")

coloredlogs.install(
    "INFO", fmt="%(asctime).19s • %(levelname).1s • %(name)s • %(message)s"
)


BASE_URL = f"https://api.polygon.io/v2/aggs/ticker"

API_KEYS = [
    "_nAIabBBWqg9knHcHJhx47Wi3qI7iRyG",
    "3rCfGdDJAMWmV459imUwajSqdj2LhIi3",
    "6Np91kVdBAJeJKJDU_oKE_XUVCq86Rj8",
    "BGJRYcypcP2SjTPTP3eAhlDWklYVFzOy",
    "bwZ_eLTGNkiH9Lp62grup3j3pGGiB82J",
    "clOPx5stlfmQ9pqDHPpH2cqPm25fB7NO",
    "dxHYh6NGEwkcopukOtv5zrgT77lzz0jc",
    "iJB8XcWEGYBUsgvh7CSehm97JlLNIggP",
    "IUmjUfgE493yWuTekHxWN9D4yYKwpkts",
    "M5k7iuwvP85rXciuBf9m3jXsuG4DtWjY",
    "pv0vzspm5lIxKDXSDwhVdsBhSGrxThvq",
    "qaT6bxMib9HKOdhIwFnrJXzOmtBxrMqG",
    "sH1_pNX3qFXcPG5lB3rp685eqNYVMXCn",
    "tSzKfPCSmpDpYHDlZljip2UpKMBvPpUH",
    "uZpnXYsLKykjn3i9KspAvBnEC19AVJFz",
    "WjySnu2xlHJUm4Ssj0xYL6iZlfm4ibIP",
    "X6v6pHhikJIparVJDnYrXhpgmgr2NJB7",
    "x7PTlD_3sTidLZZLxkjdkrEE_iqbA4YK",
    "Y56e3FBQKzWMf19hDz0F6knhyzWhjeFm",
    "YTBk_CI6S0pwzfSCJ3LBtYyAyVo1FO8u",
]

LIMIT = 50000


dt_format = click.DateTime(formats=["%Y-%m-%d %H:%M:%S"])


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def get_next_key():
    global API_KEYS
    API_KEYS = API_KEYS[1:] + [API_KEYS[0]]
    return API_KEYS[0]


def load_polygon_one_symbol(symbol, dt_1, dt_2):
    ts_1 = dt_to_ts(dt_1) * 1000
    ts_2 = dt_to_ts(dt_2) * 1000

    limit = LIMIT
    data = []

    while True:

        url = f"{BASE_URL}/{symbol}/range/1/minute/{ts_1}/{ts_2}"
        params = {
            "apiKey": get_next_key(),
            "adjusted": False,
            "sort": "asc",
            "limit": limit,
        }
        r = requests.get(url, params=params, timeout=15)

        log.debug(f"{dt_1}, {dt_2}, {r.url}")

        if r.status_code == 429:
            log.warning("API limit, wait 10 sec...")
            sleep(10)
            continue

        try:
            rj = r.json()
        except Exception as e:
            log.error(e)
            log.error(f"API request error: {r.status_code}, {r.text}")
            raise Exception("PolygonApiError")

        if err := rj.get("error"):
            log.error(f"API error: {err}")
            raise Exception("PolygonApiError")

        res = rj.pop("results", [])
        data += res

        if len(res):
            max_ts_collected = int(res[-1]["t"]) + 1000 * 60

            if len(res) < limit:
                log.debug("DONE, res under the limit")
                break

            if max_ts_collected >= ts_2:
                log.debug("DONE, got all ts")
                break

            ts_1 = max_ts_collected

        else:
            log.debug("DONE, empty")
            break

        sleep(0.1)

    return data


def get_last_interval_dt(f_path):
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
    return last_dt


def process_symbol(symbol, dt_start, dt_end, reset, latency_tolerance):
    ss = symbol.split(":")[1]

    f_path = os.path.abspath(f"../data/polygon_nyse/2022/{ss}.csv")

    dt_1 = dt_start
    dt_2 = dt_end or (datetime.utcnow() + timedelta(days=3))

    valid_file_with_data = False

    if os.path.exists(f_path):
        log.info(f"File exists {symbol}, {f_path}")

        if reset:
            # Удаление старого файла
            os.remove(f_path)
            log.info(f"File removed {symbol}")

        else:
            # Взять из файла последний интервал, для которого есть данные
            try:
                dt_1 = get_last_interval_dt(f_path)
                log.info(f"Last existing interval for {symbol}: {dt_1}")

                # Первый интервал для загрузки
                dt_1 += timedelta(minutes=1)
                valid_file_with_data = True
            except:
                log.error(f"Can't get last existing interval for {symbol}")

    if dt_1 >= dt_2 - latency_tolerance:
        log.info(f"Already has all data, skip {symbol}")
        return

    try:
        data = load_polygon_one_symbol(ss, dt_1, dt_2)
    except Exception as e:
        log.error(f"Loading data error for {symbol}: {e}")
        return

    # Polygon возвращает данные с повторением строк
    # https://github.com/polygon-io/issues/issues/215
    data_dict = dict([(row["t"], row) for row in data])
    data = sorted(data_dict.values(), key=lambda row: row["t"])

    # {"v": 5, "vw": 1, "o": 1, "c": 1, "h": 1, "l": 1, "t": 1609765320000, "n": 1}
    # vw и n иногда отсутствуют

    if not data:
        log.warning(f"No new data for {symbol}")
        return

    log.info(f"Loaded: {len(data)}")

    txt = ""

    for line in data:
        line["t"] = int(line["t"]) // 1000
        if "vw" not in line:
            line["vw"] = ""
        if "n" not in line:
            line["n"] = ""
        txt += "{t},{o},{h},{l},{c},{vw},{v},{n}\n".format(**line)

    if valid_file_with_data:
        # Дописать в старый файл
        with open(f_path, "a") as f:
            f.write(txt)
    else:
        # Создать новый файл с заголовком
        with open(f_path, "w") as f:
            f.write("t,o,h,l,c,vw,v,n\n" + txt)


@click.command()
@click.argument("symbols", nargs=-1, default=None)
@click.option("--start", type=dt_format, default="2022-01-02 00:00:00")
@click.option("--end", type=dt_format, default=None)
@click.option("--reset", is_flag=True, default=False, help="Delete cached data")
@click.option("--debug", is_flag=True, default=False)
def main(**kwargs):
    dt_start = kwargs.get("start")
    dt_end = kwargs.get("end")
    reset = kwargs.get("reset")
    debug = kwargs.get("debug")
    symbols = kwargs.get("symbols")

    log.info(f"Start: {dt_start}")
    log.info(f"End: {dt_end}")

    symbols = list(symbols)

    # Добавить символы из stdin, если туда отправили данные
    if not sys.stdin.isatty():
        for line in sys.stdin.readlines():
            symbols.append(line.strip())

    symbols = list(sorted(list(set(symbols))))

    log.info("Symbols (%s): %s..." % (len(symbols), ", ".join(symbols[:5])))

    latency_tolerance = timedelta(hours=1)

    for symbol in symbols:
        process_symbol(symbol, dt_start, dt_end, reset, latency_tolerance)


if __name__ == "__main__":
    dt = datetime.now()
    try:
        main()
        log.info("DONE")
    except KeyboardInterrupt:
        log.info("BREAK")
    log.info(f"Done in {str(datetime.now() - dt)[:-7]}")
