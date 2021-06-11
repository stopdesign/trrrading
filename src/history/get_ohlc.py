"""
Получение исторических данных из API Exante.
"""

import json
import jwt
import requests
from time import sleep
from datetime import datetime, timezone
from settings import keys


env = "live"
api_keys = getattr(keys, env)


ticker = "DIA.ARCA"
interval_size = "60"
data_type = "trades"

url = f"https://api-{env}.exante.eu/md/3.0/ohlc/{ticker}/{interval_size}"


def interval_dt(interval):
    return datetime.fromtimestamp(interval["timestamp"] // 1000)


def get_next_headers():
    global api_keys
    api_keys = api_keys[1:] + [api_keys[0]]
    key = api_keys[0]
    payload = {"iss": key[0], "sub": key[1], "aud": ["ohlc", "feed"]}
    token = jwt.encode(payload, key[2], algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def main():

    all_data = []
    size = 5000

    from_dt = datetime(year=2015, month=1, day=1)
    from_dt = from_dt.replace(tzinfo=timezone.utc).timestamp()
    from_dt = int(from_dt) * 1000

    while True:
        params = {"from": from_dt, "type": data_type, "size": size}
        res = requests.get(url, params=params, headers=get_next_headers())

        if res.status_code == 200:
            data = res.json()

            if not data:
                print("EMPTY RESPONSE")
                break

            from_dt = data[0]["timestamp"] + 1

            print(datetime.now(), len(data), interval_dt(data[0]))

            all_data += data

            with open(f"{env}-{ticker}-{data_type}-{interval_size}.jsonl", "w") as f:
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


if __name__ == "__main__":
    main()
