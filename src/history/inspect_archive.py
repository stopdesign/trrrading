import json
import os, re
import requests
import jwt
from datetime import datetime
from statistics import mean
from settings import keys
from termcolor import cprint


env = "live"
api_keys = getattr(keys, env)


def interval_dt(interval):
    return datetime.utcfromtimestamp(interval["timestamp"] // 1000)


def get_next_headers():
    global api_keys
    api_keys = api_keys[1:] + [api_keys[0]]
    key = api_keys[0]
    payload = {"iss": key[0], "sub": key[1], "aud": ["ohlc", "feed", "symbols"]}
    token = jwt.encode(payload, key[2], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def main():

    url = "https://api-live.exante.eu/md/3.0/exchanges/ARCA"
    res = requests.get(url, headers=get_next_headers())
    descriptions = {}
    for stock in res.json():
        descriptions[stock["symbolId"]] = stock["description"]

    base = os.path.abspath("../../data/arca-60/")
    print(base)
    print()

    files = []
    for file_name in os.listdir(base):
        if mtc := re.search(r"^live-([A-Z.]+)-trades-60\.jsonl$", file_name):
            files.append(mtc[0])

    # files = files[:50]

    # header
    print(f"ticker {' ' * 9} price   gap  days   ticks\n".title())

    cnt = 0
    for file in files:
        f_name = f"{base}/{file}"
        ticker = file.split("-")[1]
        size = os.path.getsize(f_name) // (1024 * 1024)

        diffs = []
        prev_dt = None
        days = set()

        line = None

        for line in open(f_name):
            dt = datetime.utcfromtimestamp(int(line[14:24]))
            if dt < datetime(2021, 1, 1):
                continue
            if prev_dt and dt.date() == prev_dt.date():
                diffs.append(int((dt - prev_dt).total_seconds()))
                days.add(dt.date())
            prev_dt = dt

        if not diffs:
            continue

        # последняя известная цена
        close = int(float(json.loads(line)["close"]))

        # среднее расстояние между тиками внутри дня
        m_diff = int(mean(diffs))

        # количество дней
        days_21 = len(days)

        # количество тиков
        l_diff = len(diffs)

        # Leverage
        d = descriptions.get(ticker, "").lower()
        lev = ""
        if "leverage" in d or "1x" in d or "2x" in d or "3x" in d or "5x" in d:
            lev = "leverage"

        if close > 20 and m_diff < 250 and days_21 > 100 and l_diff < 20000 and l_diff > 15000 and not lev:
            cnt += 1
            cprint(f"{ticker:<15}\t{close:6}{m_diff:6}{days_21:6}{l_diff:8}{size:5} MB")
        else:
            pass
            # cprint(f"{ticker:<15}\t{close:6}{m_diff:6}{days_21:6}{l_diff:8}{size:5} MB {lev}", "yellow")

    print("\n>>>>", cnt)


def get_first_line(f_name):
    f = open(f_name, "r")
    first_line = f.readline().strip()
    return first_line


def get_last_line(f_name):
    with open(f_name, "rb") as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b"\n":
            f.seek(-2, os.SEEK_CUR)
        last_line = f.readline().decode().strip()
    return last_line


def first_last_date(f_name):
    last_line = get_last_line(f_name)
    first_line = get_first_line(f_name)

    # line = ""
    # for line in f:
    #     pass
    # last_line = line.strip()

    t1 = interval_dt(json.loads(first_line))
    t2 = interval_dt(json.loads(last_line))

    color = "grey"
    if t1 > datetime(2021, 1, 1):
        color = "red"
        cprint(f"{f_name.split('/')[-1]}\t {t1}  {t2}", color)


if __name__ == "__main__":
    # first_last_date()
    main()
