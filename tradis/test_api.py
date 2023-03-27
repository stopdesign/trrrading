import json
import logging
import os
import sys
from datetime import datetime
from os.path import abspath
from random import randint
from time import sleep

from ibapi.connection import Connection
from ibapi import comm

import pytz
import redis
import yaml
from rich.pretty import pprint

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
    # sid = "CME_MES_2306"
    # sid = "CBOT_ZW_2305"
    # sid = "CBOT_ZO_2305"
    # sid = "PAXOS_ETH"
    # sid = "IDEALPRO_EUR.USD"
    sid = "ARCA_URA"

    print("SID:", sid)

    contract = ib.contract_for_sid(sid)

    print("CONTRACT:", contract)

    cd = ib.get_contract_details(contract)
    details = cd[0]
    contract = details.contract

    pprint(contract.__dict__)
    pprint(details.__dict__)

    # sid_again = ib.sid_for_contract(contract)

    # print("SID:", sid_again)


if __name__ == "__main__":
    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    live = config  # ["live"]

    redis_config = config["redis"]
    redis_client = redis.Redis(**redis_config)
    gateway = config["gateway"]

    ib = IBSync()
    client_id = 299


    # # быстрая и не зависающая проверка соединения с TWS

    # conn = Connection(gateway["host"], 4002)
    # conn.connect()

    # is_connected = conn.isConnected()
    # log.info(f"Connected: {is_connected}")

    # v100prefix = "API\0"
    # v100version = "v%d..%d" % (100, 176)

    # msg = str.encode(v100prefix, 'ascii') + comm.make_msg(v100version)
    # log.info(f"REQUEST {msg}")

    # try:
    #     bytes_sent = conn.sendMsg(msg)
    #     log.info(f"Sent: {bytes_sent}")

    #     buf = conn.recvMsg()
    #     log.info(f"ANSWER {buf}")

    #     size, msg, rest = comm.read_msg(buf)
    #     log.info(f"Size: {size}, msg: {msg}, rest: {rest}")

    #     fields = comm.read_fields(msg)
    #     log.info(f"Fields {fields}")

    # except Exception as e:
    #     log.error(f"Error: {e}")

    # conn.disconnect()
    # log.info("DONE")



    ib.connect(gateway["host"], gateway["port"], client_id)
    IBThread(ib).start()

    sleep(1)

    try:
        main(ib)
    except KeyboardInterrupt:
        print()
        print("DONE")
    finally:
        ib.disconnect()
