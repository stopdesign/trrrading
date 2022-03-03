import yaml
from os.path import abspath
from time import sleep
from termcolor import cprint
from ibkr_web_api import IbApi


def main(ib):

    while True:
        # Проверить, есть жива ли SSO-сессия
        sso = ib.sso_validate()

        # Если сессия не работает — перелогин.
        if sso.get("_ERROR") or not sso.get("USER_ID"):
            cprint(" FULL RELOGIN ", "red", attrs=['reverse'])
            ib.portal_logout()
            ib.sso_logout()
            if not ib.obtain_session():
                print("Wait before reconnect")
                sleep(10)
            continue

        # Тут должна быть живая сессия,
        # проверить аунтетнификацию в iserver.
        iserver = ib.iserver_auth_status()

        # Не проверяется — перелогин.
        if iserver.get("_ERROR") is not False:
            print("bad iserver_status", iserver)
            sleep(10)
            continue

        # Сессия есть, но iserver не authenticated.
        # Попробовать оживить.
        if not iserver.get("authenticated"):
            print("iserver is not authenticated")
            print("SOFT REAUTH")
            iserver = ib.init_iserver_session()

        # Если оживить не получилось — перелогин.
        if not iserver.get("authenticated"):
            ib.portal_logout()
            ib.sso_logout()
            continue

        cprint(" GOOD SESSION ", "green", attrs=['reverse'])

        sleep(1)

        try:
            ib.keep_session_alive()
        except Exception as e:
            cprint(f"Tickle exception {e}", "red")
            sleep(3)


if __name__ == "__main__":

    # Загрузка конфига
    config_path = abspath("config_local.yaml")
    config = yaml.full_load(open(config_path))

    username = config["username"]
    password = config["password"]
    paper = config["paper"]
    secret = config["secret"]
    redis_config = config["redis"]

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

    ib.load_session(f"session_{username}.json")

    try:
        main(ib)
    except KeyboardInterrupt:
        print("DONE")
