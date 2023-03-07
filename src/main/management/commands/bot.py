import argparse
import yaml
import logging
from datetime import datetime
from os.path import abspath, join, dirname
from django.core.management.base import BaseCommand
from django.conf import settings
# from trader import Trader
from trader2.trader import Trader2

log = logging.getLogger("run")


DEF_CONFIG = "../config/bot.yaml"


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "not a valid date: {0!r}".format(s)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--config", type=str, dest="config", default=DEF_CONFIG)
        parser.add_argument("-b", "--backtest", action="store_true")
        parser.add_argument("-r", "--replay", action="store_true")
        parser.add_argument("-s", "--start", type=valid_date, dest="dt_start")
        parser.add_argument("-e", "--end", type=valid_date, dest="dt_end")

    def handle(self, **kwargs):

        dt = datetime.utcnow()

        conf_dir = join(dirname(settings.BASE_DIR))
        config_path = abspath(join(conf_dir, kwargs.get("config")))
        config = yaml.full_load(open(config_path))

        if kwargs["dt_start"]:
            config["backtest"]["dt_start"] = kwargs["dt_start"].date()
            config["live"]["dt_start"] = kwargs["dt_start"].date()

        if kwargs["dt_end"]:
            config["backtest"]["dt_end"] = kwargs["dt_end"].date()
            config["live"]["dt_end"] = kwargs["dt_end"].date()

        backtest = bool(kwargs.get("backtest"))
        replay = bool(kwargs.get("replay"))

        assert not (backtest and replay), "Can't combine replay and backtest"

        trader = Trader2(config, backtest, replay)
        # trader.start_intervals()
        trader.start()

        print(f"Done in {str(datetime.utcnow() - dt)[:-6]}")
