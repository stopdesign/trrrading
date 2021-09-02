import os
import sys
import yaml
import click
import logging
from datetime import datetime
from termcolor import cprint
from trader import Trader


sys.path.append(os.path.abspath("."))

template = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
root = logging.getLogger()
root.setLevel(logging.INFO)
h = logging.StreamHandler(sys.stdout)
# h.setFormatter(logging.Formatter(f"\033[0;35m{template}\033[0m"))
root.addHandler(h)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(logging.Formatter(f"\033[0;35m{template}\033[0m"))

l1 = logging.getLogger('ib_insync.ib')
l1.setLevel(logging.WARNING)
l1.addHandler(h)
l1.propagate = False

l2 = logging.getLogger('ib_insync.client')
l2.setLevel(logging.WARNING)
l2.addHandler(h)
l2.propagate = False

l3 = logging.getLogger('ib_insync.wrapper')
l3.setLevel(logging.WARNING)
l3.addHandler(h)
l3.propagate = False


@click.command()
@click.argument("broker")
@click.argument("instruments")
def main(**kwargs) -> None:
    dt = datetime.now()

    broker_conf_path = kwargs.get("broker")
    instruments_conf_path = kwargs.get("instruments")

    broker = yaml.full_load(open(broker_conf_path))
    instruments = yaml.full_load(open(instruments_conf_path))

    trader = Trader(
        exchange=broker["driver"],
        instruments=instruments,
        target_margin=broker.get("target_margin"),
        dt_start=broker.get("dt_start"),
    )

    try:
        trader.warm_up()
        trader.start()
    except KeyboardInterrupt:
        trader.stop()
    finally:
        trader.final_info()

    cprint(f"\nDone in {str(datetime.now() - dt)[:-7]}", attrs=["bold"])


if __name__ == "__main__":
    main()
