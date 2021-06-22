import json
import os, re
from datetime import datetime
from statistics import mean
from urllib.parse import quote
from termcolor import cprint


def interval_dt(interval):
    return datetime.fromtimestamp(interval["timestamp"] // 1000)


def main():

    base = os.path.abspath("../../data/nasdaq/")
    print(base)
    print()

    files = []
    for file_name in os.listdir(base):
        if mtc := re.search(r"^live-([A-Z.]+)-trades-60\.jsonl$", file_name):
            files.append(mtc[0])

    files = files[:50]

    cnt = 0
    for file in files:
        f_name = f"{base}/{file}"
        # first_last_date(f_name)

        diffs = []
        prev_dt = None
        f = open(f_name, "r")
        days = set()
        for line in f:
            dt = interval_dt(json.loads(line))
            if dt < datetime(2021, 1, 1):
                continue
            if prev_dt and dt.date() == prev_dt.date():
                diffs.append(int((dt - prev_dt).total_seconds()))
                days.add(dt.date())
            prev_dt = dt

        m_diff = int(mean(diffs))
        days_2021 = len(days)
        l_diff = len(diffs)

        if m_diff < 250 and days_2021 > 100 and l_diff > 20000:
            cnt += 1
            print(f"{file}\t{m_diff:8.0f}{l_diff:8.0f}{days_2021:8.0f}")

    print(">>>>", cnt)


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
