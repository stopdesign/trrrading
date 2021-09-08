import sys
import yaml
import json
import click
import logging
from os.path import abspath, join, dirname
from datetime import datetime
from trader import Trader

sys.path.append(abspath("."))

log = logging.getLogger("main")

dt_format = click.DateTime(formats=["%Y-%m-%d"])


@click.command()
@click.argument("broker")
@click.argument("instruments")
@click.option("--dt-start", "--dt_start", "--start", type=dt_format)
@click.option("--dt-end", "--dt_end", "--end", type=dt_format)
def main(**kwargs) -> None:
    dt = datetime.now()

    base_dir = abspath(dirname(__file__))
    broker_conf_path = abspath(join(base_dir, kwargs.get("broker")))
    instruments_conf_path = abspath(join(base_dir, kwargs.get("instruments")))

    # Загрузка конфига
    broker_conf = yaml.full_load(open(broker_conf_path))
    instruments_conf = yaml.full_load(open(instruments_conf_path))

    if kwargs["dt_start"]:
        broker_conf["dt_start"] = kwargs["dt_start"].date()

    if kwargs["dt_end"]:
        broker_conf["dt_end"] = kwargs["dt_end"].date()

    # Записать конфиг в логи
    log.debug(json.dumps(broker_conf, default=str))
    log.debug(json.dumps(instruments_conf, default=str))

    trader = Trader(broker_conf, instruments_conf, base_dir)

    try:
        trader.warm_up()
        trader.start()
    except KeyboardInterrupt:
        trader.stop()
    except Exception as e:
        log.exception(e)
    finally:
        trader.final_info()

    log.info(f"Done in {str(datetime.now() - dt)[:-7]}")


if __name__ == "__main__":
    main()
