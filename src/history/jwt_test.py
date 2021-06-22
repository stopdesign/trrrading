import json

import jwt
import requests
from datetime import datetime, timezone, timedelta

# env = "live"
# client_id = "fefca6db-f62e-4c62-8f5c-e4d588a6090e"
# app_id = "08fefb9d-8a05-4b47-8b5f-075c91d87a3a"
# shared_key = "76xvX0dEm8wSA/d/YzIH4CWptgrb/4KO"

env = "demo"
client_id = "40dd4b62-8296-46ff-9b6d-367ad9a35aed"
app_id = "72d39665-3477-4b48-aba6-b5688a0ab529"
shared_key = "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp"


base = f"https://api-{env}.exante.eu"

dt_from = datetime.now()
dt_from = int(dt_from.replace(tzinfo=timezone.utc).timestamp())

dt_exp = datetime.now() + timedelta(days=30)
dt_exp = int(dt_exp.replace(tzinfo=timezone.utc).timestamp())

perms = ["ohlc", "feed", "orders", "summary", "accounts", "symbols"]
# perms = ["ohlc"]
payload = {
    "iss": client_id,
    "sub": app_id,
    "aud": perms,
}

token = jwt.encode(payload, shared_key, algorithm="HS256")
print(json.dumps(payload, indent=2, default=str))
print(token)


account_id = "UEA7232.001"
ver = "3.0"
cur = "USD"

url_account = f"{base}/md/{ver}/summary/{account_id}/{cur}"
url_orders = f"{base}/trade/{ver}/orders"
url_ohlc = f"{base}/md/{ver}/ohlc/SPY.ARCA/60?size=2"
url_symbols = f"{base}/md/{ver}/symbols"

headers = {"Authorization": f"Bearer {token}"}

res = requests.get(url_orders, headers=headers)
print(res.status_code)
try:
    print(json.dumps(res.json(), indent=2, default=str))
except:
    print(res.text)
