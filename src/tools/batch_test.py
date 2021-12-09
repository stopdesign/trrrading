import os
import re
import yaml
import logging
from datetime import datetime, date, timedelta
from termcolor import cprint
from trader.trader import Trader
from multiprocessing import Pool
from os.path import abspath, join, dirname


PROCESSES = 1  # cpu_count()


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


def alldays(year, day=0):
    """
    0 == monday
    """
    d = date(year, 1, 1)
    d += timedelta(days=(day - d.weekday()) % 7)
    while d.year == year:
        yield d
        d += timedelta(days=7)


def main() -> None:
    dt = datetime.now()

    # symbols = get_stored_symbols()
    # symbols = [
    #     "AMZA.ARCA", "APH.ARCA", "ARKK.ARCA", "BLOK.ARCA", "COPX.ARCA",
    #     "COPY.ARCA", "EMQQ.ARCA", "GPK.ARCA", "INVH.ARCA", "MS.ARCA",
    #     "NVDA.ARCA", "OIH.ARCA", "ROBO.ARCA", "SIL.ARCA", "SPY.ARCA",
    #     "TAN.ARCA", "URA.ARCA", "XOP.ARCA"
    # ]
    symbols = [
        # "M2K.GLOBEX",
        # "MNQ.GLOBEX",
        # "MES.GLOBEX",
        # "COPX.ARCA",
        "URA.ARCA"
        # "FCX.NYSE",
    ]

    params = []

    base_dir = abspath(dirname(__file__))

    broker_conf_path = abspath(join(base_dir, "../backtest.yaml"))
    broker_conf = yaml.full_load(open(broker_conf_path))

    lst = [30, 35, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200]

    for symbol in sorted(symbols):
        # for length in [10, 50, 100, 200, 400, 600, 800]:
        # for r in [0.2, 0.4, 0.6, 0.8, 1, 1.5, 2]:
        # r = 0.42
        for length in lst:
            advisor = {
                "strategy": "ChannelBreakout3",
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
        return params, trader.account_stats.print_short_summary()
    except Exception as e:
        # cprint(f"err: {e}", "red")
        return params, -100


if __name__ == "__main__":
    main()
