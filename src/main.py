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


@click.command()
@click.argument("broker")
@click.argument("instruments")
def main(**kwargs) -> None:
    dt = datetime.now()

    base_dir = abspath(dirname(__file__))
    broker_conf_path = abspath(join(base_dir, kwargs.get("broker")))
    instruments_conf_path = abspath(join(base_dir, kwargs.get("instruments")))

    # Загрузка конфига
    broker = yaml.full_load(open(broker_conf_path))
    instruments = yaml.full_load(open(instruments_conf_path))

    # Записать конфиг в логи
    log.debug(json.dumps(broker, default=str))
    log.debug(json.dumps(instruments, default=str))

    driver = broker["driver"]
    margin = broker.get("target_margin")
    dt_start = broker.get("dt_start")
    trader = Trader(driver, instruments, margin, base_dir, dt_start)

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
