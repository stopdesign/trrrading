import argparse
import yaml
import logging
from datetime import datetime
from os.path import abspath, join, dirname
from django.core.management.base import BaseCommand
from django.conf import settings
from trader import Trader

log = logging.getLogger("run")


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

        parser.add_argument('--backtest', action=argparse.BooleanOptionalAction)
        parser.add_argument('--start', type=valid_date, dest="dt_start")
        parser.add_argument('--end', type=valid_date, dest="dt_end")

    def handle(self, *args, **kwargs):

        dt = datetime.utcnow()

        conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))
        strategy_config_path = abspath(join(conf_dir, kwargs.get("strategy")))

        # Загрузка конфига
        broker_config = yaml.full_load(open(broker_config_path))
        strategy_config = yaml.full_load(open(strategy_config_path))  # instruments

        if kwargs["dt_start"]:
            broker_config["dt_start"] = kwargs["dt_start"].date()

        if kwargs["dt_end"]:
            broker_config["dt_end"] = kwargs["dt_end"].date()

        backtest = bool(kwargs.get("backtest"))

        trader = Trader(broker_config, strategy_config, backtest)

        try:
            trader.warm_up()
            trader.start()
        except KeyboardInterrupt:
            trader.stop()
        except Exception as e:
            log.exception(e)
        finally:
            trader.final_info()

        print(f"Done in {str(datetime.utcnow() - dt)[:-7]}")
