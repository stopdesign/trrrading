import logging
from datetime import datetime
from os.path import abspath

import coloredlogs
import redis
import yaml
from ibkr_web_api import IBClient
from ibkr_web_api.alert import TelegramAlertHandler
from ibkr_web_api.storage import RedisStorage
from ibkr_web_api.utils.ocra import ocra_handler

# Логгер для этого файла
log = logging.getLogger("session_keeper")
log.setLevel(logging.INFO)

coloredlogs.install(
    "INFO", fmt="%(asctime).19s • %(levelname).1s • %(name)s • %(message)s"
)


def main():

    # Загрузка конфига
    config = yaml.full_load(open(abspath("../config/tradis.yaml")))

    username = config["username"]
    password = config["password"]
    paper = config["paper"]

    if redis_config := config.get("redis"):
        redis_client = redis.Redis(**redis_config)
        rs = RedisStorage(username, redis_client, config["secret"])
    else:
        rs = None

    if telegram_config := config.get("telegram"):
        ah = TelegramAlertHandler(**telegram_config)
    else:
        ah = None

    ib = IBClient(username, password, paper, storage=rs, alert_handler=ah)
    ib._auth.ibkey_handler = ocra_handler

    # TODO: add "force new session" flag?
    ib.load_session()

    # TODO: разобраться с заменой base_url
    # ib._session.reset_state()
    # ib._session.base_url = "https://cdcdyn.interactivebrokers.com"

    ib.check_bulletins()

    ib.keep_connected()


if __name__ == "__main__":
    dt = datetime.now()
    try:
        main()
    except KeyboardInterrupt:
        pass
    print(f"\nDone in {str(datetime.now() - dt)[:-7]}")
