"""
Получение исторических данных из API Exante.

Токен брать тут:
https://exante.eu/clientsarea/dashboard/

"""

import json
import requests
from time import sleep
from datetime import datetime, timezone


token = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJmZWZjYTZkYi1mNjJlLTR"
    "jNjItOGY1Yy1lNGQ1ODhhNjA5MGUiLCJzdWIiOiIwOGZlZmI5ZC04YTA1LTRiNDctOGI"
    "1Zi0wNzVjOTFkODdhM2EiLCJpYXQiOjE2MjI0NjkxNzUsImV4cCI6MTYyNTA2MTE3NSw"
    "iYXVkIjpbIm9obGMiLCJmZWVkIiwib3JkZXJzIiwic3VtbWFyeSIsImFjY291bnRzIl1"
    "9.ZSyrFCPDuVUwx-uDTJQNMWsSASLIHsSgO0NYgj5b7J8"
)

env = "live"
ticker = "SPY.ARCA"
interval_size = "60"
data_type = "trades"

url = f"https://api-{env}.exante.eu/md/3.0/ohlc/{ticker}/{interval_size}"


def interval_dt(interval):
    return datetime.fromtimestamp(interval["timestamp"] // 1000)


def main():

    all_data = []

    from_dt = datetime(year=2021, month=6, day=1)
    from_dt = from_dt.replace(tzinfo=timezone.utc).timestamp()
    from_dt = int(from_dt) * 1000

    while True:
        params = {
            "token": token,
            "from": from_dt,
            "type": data_type,
            "size": 5000,
        }
        res = requests.get(url, params=params)

        if res.status_code == 200:
            data = res.json()

            if not data:
                print("EMPTY RESPONSE")
                break

            from_dt = data[0]["timestamp"] + 1

            print(datetime.now(), len(data), interval_dt(data[0]))

            all_data += data

            with open(f"test-{env}-{ticker}-{data_type}-{interval_size}.jsonl", "w") as f:
                res = ""
                for interval in all_data:
                    res += json.dumps(interval, indent=None, default=str) + "\n"
                f.write(res)

            if len(data) <= 10:
                print("ALL DONE")
                break

            sleep(60)

        elif res.status_code == 429:
            print("429")
            sleep(10)

        else:
            print(res.status_code)
            print(res.text)
            break


if __name__ == "__main__":
    main()
