import argparse
import json
import yaml
from datetime import datetime, timedelta
from secrets import token_hex
from time import sleep
from os.path import abspath, join, dirname
from django.core.management.base import BaseCommand
from ibkr_web_api import IbApi
from main.models import Run, Order, Instrument, Position, Account
from termcolor import cprint
from django.conf import settings


# username = "vysoch218"
from trader import Trader

username = "gr5g2ry0"
password = ""
paper = True

ib = IbApi(username, password, paper, debug=False)


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "not a valid date: {0!r}".format(s)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('broker', type=str)
        parser.add_argument('strategy', type=str)

        parser.add_argument('--start', type=valid_date, dest="dt_start")
        parser.add_argument('--end', type=valid_date, dest="dt_end")

    def handle(self, *args, **kwargs):

        dt = datetime.utcnow()

        conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))
        strategy_config_path = abspath(join(conf_dir, kwargs.get("strategy")))

        # Загрузка конфига
        broker_config = yaml.full_load(open(broker_config_path))
        strategy_config = yaml.full_load(open(strategy_config_path))

        if kwargs["dt_start"]:
            broker_config["start"] = kwargs["dt_start"].date()

        if kwargs["dt_end"]:
            broker_config["dt_end"] = kwargs["dt_end"].date() + timedelta(1)

        account = Account.objects.get(id=3)

        run = Run(
            account=account,
            broker_config=json.dumps(broker_config, indent=2, default=str),
            strategy_config=json.dumps(strategy_config, indent=2, default=str),
        )
        run.save()

        base_dir = "/Users/gregory/projects/life/trrrading"
        trader = Trader(broker_config, strategy_config, base_dir, run)

        try:
            trader.warm_up()
            trader.start()
        except KeyboardInterrupt:
            trader.stop()
        except Exception as e:
            print(e)
        finally:
            trader.final_info()

        # log.info(f"Done in {str(datetime.utcnow() - dt)[:-7]}")

        print("RUN DONE")
