"""
Получение исторических данных из API Exante.
"""

import json
import jwt
import requests
from time import sleep
from datetime import datetime, timezone, timedelta
from util import interval_dt


# env = "demo"
# client_id = "40dd4b62-8296-46ff-9b6d-367ad9a35aed"
# app_id = "72d39665-3477-4b48-aba6-b5688a0ab529"
# shared_key = "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp"

env = "live"
client_id = "fefca6db-f62e-4c62-8f5c-e4d588a6090e"
app_id = "08fefb9d-8a05-4b47-8b5f-075c91d87a3a"
shared_key = "76xvX0dEm8wSA/d/YzIH4CWptgrb/4KO"

base = f"https://api-{env}.exante.eu"
account_id = "UEA7232.001"
# ticker = "AXON.NYSE"
ticker = "AXON.NASDAQ"  # STMP
ver = "3.0"
interval = 60

dt_from = datetime.now()
dt_from = int(dt_from.replace(tzinfo=timezone.utc).timestamp())

dt_exp = datetime.now() + timedelta(days=1)
dt_exp = int(dt_exp.replace(tzinfo=timezone.utc).timestamp())

permissions = ["ohlc", "feed"]
payload = {
    "iss": client_id,
    "sub": app_id,
    "iat": dt_from,
    "exp": dt_exp,
    "aud": permissions,
}
token = jwt.encode(payload, shared_key, algorithm="HS256")
auth_headers = {
    "Authorization": f"Bearer {token}",
}
url_tick = f"{base}/md/3.0/ticks/{ticker}"


def main():
    from_dt = datetime(year=2018, month=1, day=1)
    for data_type in ["quotes", "trades"]:
        print()
        print(data_type)
        fetch_data(data_type, from_dt)


def fetch_data(data_type, from_dt):
    from_dt = int(from_dt.replace(tzinfo=timezone.utc).timestamp()) * 1000
    all_data = []
    while True:
        params = {
            "type": data_type,
            "from": from_dt,
            "size": 5000,
        }
        res = requests.get(url_tick, params=params, headers=auth_headers)

        if res.status_code == 200:
            data = res.json()
            if not data:
                print("EMPTY RESPONSE")
                break

            from_dt = data[0]["timestamp"] + 1

            print(datetime.now(), len(data), interval_dt(data[0]))

            all_data += data

            all_data = [json.loads(t) for t in {json.dumps(d) for d in all_data}]
            all_data = sorted(all_data, key=lambda x: x["timestamp"])

            with open(f"{env}-{ticker}-{data_type}-ticks.jsonl", "w") as f:
                res = ""
                for interval in all_data:
                    res += json.dumps(interval, indent=None, default=str) + "\n"
                f.write(res)

            if len(data) <= 50:
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
