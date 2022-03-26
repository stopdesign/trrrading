import json
from os.path import abspath
import yaml
from ibkr_web_api import IbApi


def main(ib):

    ib.load_redis_session()
    # ib.load_session()

    ib.accounts()

    ib.sso_validate()
    ib.iserver_auth_status()

    # ib.print_cookies()

    acnt = ib.accounts().get("accounts")[0]
    print(acnt)

    h = ib.history()
    # print(json.dumps(h, indent=2, default=str))
    # ib.snapshot_md()
    # ib.cancel_all_orders(acnt)
    # ib.reset_session()
    # ib.load_session()
    # ib.order_details(1111)

    # ib.contract_details(211651685)

    # ib.reset_session()
    # ib.load_session()

    # print()
    # res = ib.account_summary(acnt)
    # print(res.json()["netliquidation"])
    # print()

    # ib.portal_logout()
    # ib.sso_logout()


if __name__ == "__main__":

    # Загрузка конфига
    config_path = abspath("config_local.yaml")
    config = yaml.full_load(open(config_path))

    username = config["username"]
    password = config["password"]
    paper = config["paper"]
    secret = config["secret"]
    redis_config = config["redis"]

    instruments = config["instruments"]

    dashboard_csv_path = config["dashboard_csv_path"]

    ib = IbApi(
        username,
        password,
        paper,
        secret=secret,
        debug=False,
        redis_host=redis_config["host"],
        redis_port=redis_config["port"],
        redis_db=redis_config["db"],
        redis_password=redis_config["password"],
    )

    try:
        main(ib)
    except KeyboardInterrupt:
        print("DONE")
