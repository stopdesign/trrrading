import argparse
import yaml
import logging
from dateutil import rrule
from dateutil import relativedelta as rd
from datetime import datetime, timedelta
from os.path import abspath, join, dirname
from django.core.management.base import BaseCommand
from django.conf import settings
from trader import Trader

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
        # parser.add_argument("-b", "--backtest", action="store_true")
        # parser.add_argument("-r", "--replay", action="store_true")
        parser.add_argument("-s", "--start", type=valid_date, dest="dt_start")
        parser.add_argument("-e", "--end", type=valid_date, dest="dt_end")

    def handle(self, **kwargs):

        dt = datetime.utcnow()

        conf_dir = join(dirname(settings.BASE_DIR))
        config_path = abspath(join(conf_dir, kwargs.get("config")))
        config = yaml.full_load(open(config_path))

        if kwargs["dt_start"]:
            config["backtest"]["dt_start"] = kwargs["dt_start"].date()

        if kwargs["dt_end"]:
            config["backtest"]["dt_end"] = kwargs["dt_end"].date()

        # dt_1 = datetime(2022, 8, 3)
        # dt_2 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        results = []

        # for d in rrule.rrule(rrule.WEEKLY, dtstart=dt_1, until=dt_2, byweekday=rd.SU):
        #     config["backtest"]["dt_start"] = d - timedelta(weeks=4)
        #     config["backtest"]["dt_end"] = d

        #     trader = Trader(config, backtest=True, replay=False)
        #     trader.start()
            
        #     results.append(trader.portfolio.get_info())

        for n in range(10):
            config["strategies"][0]["length"] = 100 + n * 10

            trader = Trader(config, backtest=True, replay=False)
            trader.start()
            
            results.append(trader.portfolio.get_info())

        print()
        for res in results:
            print(res)
        print()

        print(f"Done in {str(datetime.utcnow() - dt)[:-6]}")
