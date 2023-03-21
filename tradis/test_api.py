import json
from random import randint
import redis
import logging
import sys
from os.path import abspath
import yaml
import pytz
from datetime import datetime
import os

# Зачем-то это нужно
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime).19s - %(levelname).1s - %(name)s - %(message)s",
)
# Логгер для этого файла
log = logging.getLogger("session_keeper")
log.setLevel(logging.INFO)

p = os.path.abspath("..")
if p not in sys.path:
    sys.path.insert(0, p)

from src.ibkr_api.client import IBThread
from src.ibkr_api.ib_sync import IBSync



ptz = pytz.timezone("US/Pacific")


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts / 1000)


def main(ib: IBSync):

    sid = "PAXOS_ETH.USD"

    print("SID:", sid)

    contract = ib.contract_for_sid(sid)

    print("CONTRACT:", contract)

    # cd = ib.get_contract_details(contract)
    # details = cd[0]
    # contract = details.contract

    sid_again = ib.sid_for_contract(contract)

    print("SID:", sid_again)


if __name__ == "__main__":

    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    live = config  #["live"]

    redis_config = config["redis"]
    redis_client = redis.Redis(**redis_config)

    # gateway_config =

    ib = IBSync()

    try:
        main(ib)
    except KeyboardInterrupt:
        print("DONE")
