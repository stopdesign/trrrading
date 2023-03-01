import logging
import sys
import json
from datetime import datetime
from os.path import abspath

import redis
import yaml
from ibkr_web_api import IBClient
from ibkr_web_api.storage import RedisStorage
from ibkr_web_api.utils.ocra import ocra_handler
from termcolor import cprint

from time import sleep


# Зачем-то это нужно
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime).19s - %(levelname).1s - %(name)s - %(message)s",
)
# Логгер для этого файла
log = logging.getLogger("session_keeper")
log.setLevel(logging.INFO)


def main():

    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    print("CONFIG:")
    config.pop("instruments", None)
    print(json.dumps(config, indent=2))

    username = config["username"]
    password = config["password"]
    paper = config["paper"]

    redis_config = config["redis"]

    if redis_config:
        redis_client = redis.Redis(**redis_config)
        rs = RedisStorage(username, redis_client, config["secret"])
    else:
        rs = None

    ib = IBClient(username, password, paper, storage=rs)
    ib._auth.ibkey_handler = ocra_handler

    ib.load_session()

    ib.market_data.history_test()

    sleep(1)

    print("-------")
    res = ib.accounts.orders()
    print(res)
    print("-------")

    sleep(3)

    print("-------")
    res = ib.accounts.accounts()
    print(res)
    print("-------")

    sleep(3)

    print("-------")
    res = ib.accounts.orders()
    print(res)
    print("-------")
    
    # print("-------")
    # print(json.dumps(ib._session.dump(), indent=2, default=str))
    # print("-------")

    # sso, auth, competing = ib.check_session()

    # print("-------")
    # cprint(f"SSO: {sso}, authenticated: {auth}, competing: {competing}", "blue")

    # if auth:
    #     print("-------")
    #     ib.market_data.history_test()


if __name__ == "__main__":
    dt = datetime.now()
    try:
        main()
    except KeyboardInterrupt:
        pass
    print(f"\nDone in {str(datetime.now() - dt)[:-7]}")
