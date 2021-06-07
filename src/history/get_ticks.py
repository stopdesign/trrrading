"""
Получение исторических данных из API Exante.
"""

import json
import jwt
import requests
from time import sleep
from datetime import datetime, timezone, timedelta
from util import interval_dt
import pandas_market_calendars as mcal
from settings import keys


env = "demo"
api_keys = getattr(keys, env)


ticker = "SPY.ARCA"
base = f"https://api-{env}.exante.eu"
url_tick = f"{base}/md/3.0/ticks/{ticker}"


def get_next_headers():
    global api_keys
    api_keys = api_keys[1:] + [api_keys[0]]
    key = api_keys[0]
    payload = {"iss": key[0], "sub": key[1], "aud": ["ohlc", "feed"]}
    token = jwt.encode(payload, key[2], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def fetch_data(data_type, dt_from):

    all_data = []
    size = 5000
    dt_from = int(dt_from.replace(tzinfo=timezone.utc).timestamp()) * 1000

    while True:
        params = {"type": data_type, "from": dt_from, "size": size}
        res = requests.get(url_tick, params=params, headers=get_next_headers())

        if res.status_code == 200:
            data = res.json()
            if not data:
                print("EMPTY RESPONSE")
                break

            dt_from = data[0]["timestamp"] + 1

            all_data += data

            all_data = [json.loads(t) for t in {json.dumps(d) for d in all_data}]
            all_data = sorted(all_data, key=lambda x: x["timestamp"])

            with open(f"{env}-{ticker}-{data_type}-ticks.jsonl", "w") as f:
                res = ""
                for interval in all_data:
                    res += json.dumps(interval, indent=None, default=str) + "\n"
                f.write(res)

            if len(data) < size:
                print("ALL DONE")
                break

            sleep(1)

        elif res.status_code == 429:
            print("429")
            sleep(5)

        else:
            print(res.status_code)
            print(res.text)
            break


def count_back_trading_minutes(exchange, dt, minutes):
    """
    Отсчитывает minutes минут назад от dt
    с учетом рабочего расписания биржи.
    """
    cal = mcal.get_calendar(exchange)
    schedule = cal.schedule(start_date=dt - timedelta(days=20), end_date=dt)
    all_minutes = 0
    for day, t in sorted(schedule.T.to_dict("list").items(), reverse=True):
        t0, t1 = min(dt, t[0].to_pydatetime()), min(dt, t[1].to_pydatetime())
        day_minutes = (t1 - t0).total_seconds() // 60
        if day_minutes and day_minutes + all_minutes >= minutes:
            return t[1] - timedelta(minutes=minutes - all_minutes)
        all_minutes += day_minutes


def main():
    # dt_from = datetime(year=2021, month=6, day=4)

    now = datetime.now().astimezone(timezone.utc)
    dt_from = count_back_trading_minutes("NYSE", now, 500)

    for data_type in ["quotes", "trades"]:
        print()
        print(data_type, dt_from)
        fetch_data(data_type, dt_from)


if __name__ == "__main__":
    main()
