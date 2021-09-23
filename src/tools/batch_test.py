import os
import re
import yaml
import logging
from datetime import datetime
from termcolor import cprint
from trader.trader import Trader
from multiprocessing import Pool, cpu_count
from os.path import abspath, join, dirname


PROCESSES = 3  # cpu_count()


root = logging.getLogger()
root.setLevel(logging.CRITICAL)


def get_stored_symbols():
    symbols = []
    for file_name in os.listdir("../data/arca-300/"):
        if mtc := re.search(r"^live-([A-Z.]+)-trades-\d+\.jsonl$", file_name):
            symbols.append(mtc[1])
    return symbols


def read_line_ts(f, byte=0):
    f.seek(byte)
    lines = f.readlines(1000)
    return int(lines[1][14:27]) // 1000


def main() -> None:
    dt = datetime.now()

    # symbols = get_stored_symbols()
    symbols = [
        "AMZA.ARCA", "APH.ARCA", "ARKK.ARCA", "BLOK.ARCA", "COPX.ARCA",
        "COPY.ARCA", "EMQQ.ARCA", "GPK.ARCA", "INVH.ARCA", "MS.ARCA",
        "NVDA.ARCA", "OIH.ARCA", "ROBO.ARCA", "SIL.ARCA", "SPY.ARCA",
        "TAN.ARCA", "URA.ARCA", "XOP.ARCA"
    ]
    symbols = ["URA.ARCA"]

    params = []

    base_dir = abspath(dirname(__file__))

    broker_conf_path = abspath(join(base_dir, "../backtest.yaml"))
    broker_conf = yaml.full_load(open(broker_conf_path))

    for symbol in sorted(symbols):
        # for length in [10, 50, 100, 200, 400, 600, 800]:
        # for r in [0.2, 0.4, 0.6, 0.8, 1, 1.5, 2]:
        # r = 0.42
        for length in [20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 180, 210]:
            advisor = {
                "strategy": "ChannelBreakout3",
                # "range": r,
                "length": length,
            }
            conf = {
                "short": True,
                "advisors": [advisor],
            }
            params.append((broker_conf, {symbol: conf}, base_dir))

    with Pool(processes=PROCESSES) as pool:
        for _ in pool.imap_unordered(run_trader, params):
            pass

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=["bold"])


def run_trader(params):
    try:
        trader = Trader(*params)
        trader.warm_up()
        trader.start()
        trader.account_stats.print_short_summary()
    except Exception as e:
        cprint(e, "red")


if __name__ == "__main__":
    main()
