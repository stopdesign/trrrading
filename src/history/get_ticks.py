"""
Получение исторических данных из API Exante.
"""

import json
import jwt
import requests
from time import sleep
from datetime import datetime, timezone
from settings import keys
from util import interval_dt
from termcolor import cprint

env = "live"
api_keys = getattr(keys, env)


ticker = "URNM.ARCA"
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
        try:
            res = requests.get(
                url_tick, params=params, headers=get_next_headers(), timeout=15,
            )
        except requests.exceptions.RequestException as e:
            cprint(f"{e!s}", color="red")
            sleep(3)
            continue

        if res.status_code == 200:
            data = res.json()
            if not data:
                print("EMPTY RESPONSE")
                break

            dt_from = data[0]["timestamp"] + 1

            print(datetime.now().time(), len(data), interval_dt(data[0]))

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

            sleep(3)

        elif res.status_code == 429:
            print("429")
            sleep(5)

        else:
            print(res.status_code)
            print(res.text)
            break


def main():
    dt_from = datetime(year=2018, month=1, day=1)

    for data_type in ["trades", "quotes"]:
        print()
        print(data_type, dt_from)
        fetch_data(data_type, dt_from)


if __name__ == "__main__":
    main()
