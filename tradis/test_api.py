import json
from random import randint
import redis
import logging
import sys
from os.path import abspath
import yaml
import pytz
from datetime import datetime
from ibkr_web_api import IBThinClient, RedisStorage

# Зачем-то это нужно
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime).19s - %(levelname).1s - %(name)s - %(message)s",
)
# Логгер для этого файла
log = logging.getLogger("session_keeper")
log.setLevel(logging.INFO)


ptz = pytz.timezone("US/Pacific")


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts / 1000)


def main(ib: IBThinClient, account_uid):

    ib.load_session()

    print("\naccounts:")
    res = ib.accounts.accounts()
    print(res.json)

    # res = ib.trsrv.secdef(497954518)
    # print(json.dumps(res.json, indent=2))

    # res = ib.trsrv.futures("MES")
    # print(json.dumps(res.json, indent=2))

    # res = ib.market_data.contract_algos(265598)
    # print(json.dumps(res.json, indent=2))

    # Работает
    # order_data = {
    #     "conid": 265598,
    #     "cOID": "test-%s" % randint(10000, 99999),
    #     # "secType": "265598:STK",  # Без этого тоже работает
    #     "orderType": "MKT",
    #     "price": 152,
    #     "side": "BUY",
    #     "tif": "GTC",
    #     "quantity": 1,
    #     "outsideRTH": True,
    #     "useAdaptive": False,
    # }

    # "Urgent",
    # "Normal",
    # "Patient",

    # # Adaptive работает. Бывает MKT и LMT.
    # order_data = {
    #     "conid": 497954518,
    #     # "secType": "*****:STK",
    #     "cOID": "***-%s" % randint(10000, 99999),
    #     "orderType": "MKT",
    #     # "price": 152,
    #     "side": "BUY",
    #     "tif": "DAY",  # GTC orders are not allowed for Adaptive IB algorithmic orders
    #     "quantity": 2,
    #     # "strategy": "Adaptive",
    #     # "outsideRTH": True,  # Only RTH orders are allowed for IB algorithmic orders
    #     # "useAdaptive": False,  # Кажется, ни на что не влияет
    #     # "strategyParameters": {
    #         # "adaptivePriority": "Urgent",
    #     # },
    #     "conditions": "013a120220829 14:00:00",
    #     "dfasdf": "sddd",
    # }

    # print()
    # print("===")
    # print()
    # res = ib.accounts.place_order(account_uid, order_data, confirm=True)
    # print(json.dumps(res.json, indent=2))

    # aapl 265598
    # mnts 508109460
    res = ib.market_data.history(415578518, period="700min", bar="1min", rth=False)
    print(json.dumps(res.json, indent=2))

    # account = res.json["accounts"][0]

    # print("\norders:")
    # res = ib.accounts.orders()
    # print(json.dumps(res.json, indent=2))
    # print(len(res.json["orders"]))

    # print("\norder_status:")
    # res = ib.accounts.order_status(791483489)
    # print(json.dumps(res.json, indent=2))

    # print("\nportfolio accounts:")
    # res = ib.portfolio.accounts()
    # print(res.json)

    # print("\nportfolio summary:")
    # res = ib.portfolio.summary(account)

    # for k, v in dict(res.json).items():
    #     print(k, v["amount"])

    # netliquidation = res.json["netliquidation"]["amount"]
    # print("netliquidation:", netliquidation)

    # print("\nportfolio positions:")
    # res = ib.portfolio.positions_2(account)
    # for pos in res.json:
    #     print(pos)


if __name__ == "__main__":

    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    live = config  #["live"]

    username = live["username"]
    # account = live["account"]
    account = "DU5035855"
    secret = live["secret"]

    # redis_config = config["sources"]["redis_local"]

    redis_config = config["redis"]

    redis_client = redis.Redis(**redis_config)
    rs = RedisStorage(username, redis_client, secret)

    ib = IBThinClient(username, rs)

    try:
        main(ib, account)
    except KeyboardInterrupt:
        print("DONE")
