import json
import os
import re
from datetime import datetime, timedelta
from termcolor import cprint
from advisor import Advisor
from tester import Tester
from multiprocessing import Pool, cpu_count


PROCESSES = 3  # cpu_count()


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
    # symbols = ["EMQQ.ARCA"]
    symbols = [
        "AMZA.ARCA",
        "ARKK.ARCA",
        "ARKW.ARCA",
        "BLOK.ARCA",
        "CHIQ.ARCA",
        "COPX.ARCA",
        "CQQQ.ARCA",
        "EMQQ.ARCA",
        "EPOL.ARCA",
        "FDN.ARCA",
        "GUNR.ARCA",
        "ITOT.ARCA",
        "IWP.ARCA",
        "IXC.ARCA",
        # "JNK.ARCA",
        "OIH.ARCA",
        "ROBO.ARCA",
        "URA.ARCA",
        "VCR.ARCA",
        "VDE.ARCA",
        "XSD.ARCA",
    ]

    strategy = "ChannelBreakout"
    extra_data = False

    dt_start = datetime(2018, 3, 1)

    params = []

    for symbol in sorted(symbols):
        exchange = symbol.split(".")[1]
        trades_file = f"../data/{exchange.lower()}-60/live-{symbol}-trades-60.jsonl"
        with open(trades_file) as f:
            ts = read_line_ts(f)
            dt_start = max(dt_start, datetime.utcfromtimestamp(ts) + timedelta(days=55))

        print(f"\n{symbol}\t{dt_start:%Y-%m-%d}")

        # for length in [450]:
        for length in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1200]:
            params.append((dt_start, extra_data, length, strategy, symbol))

    with Pool(processes=PROCESSES) as pool:
        for _ in pool.imap_unordered(test_params, params):
            pass

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=["bold"])


def test_params(params):
    dt_start, extra_data, length, strategy, symbol = params
    advisors = [
        Advisor(strategy, symbol, length=length, extra_data=extra_data),
    ]
    test_name = f"{symbol}_{strategy}_{length}"
    try:
        tester = Tester(advisors, dt_start=dt_start)
        tester.start()
        tester.stop()
        roi, max_dd, cnt, pf, r2, roi_dd = tester.get_stats(test_name)
    except Exception as e:
        cprint(e, "red")
        return "error"
    res = (
        f"{symbol}\t{dt_start:%Y-%m-%d}\t{strategy}\t{length}\t{extra_data}\t"
        f"{roi:0.2f}\t{max_dd:0.2f}\t"
        f"{cnt}\t{pf:0.2f}\t{r2:0.2f}\t{roi_dd:0.2f}\n"
    )
    with open("batch.csv", "a") as batch:
        batch.write(res)
    return "ok"


if __name__ == "__main__":
    main()
