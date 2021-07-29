import logging
from datetime import datetime
from termcolor import cprint
from advisor import Advisor
from trader import Trader

import sys, os
sys.path.append(os.path.abspath("."))


# Чтобы логи валились в stdout
root = logging.getLogger()
root.setLevel(logging.DEBUG)
root.addHandler(logging.StreamHandler(sys.stdout))


def main() -> None:
    dt = datetime.now()

    advisors = [
        Advisor("ChannelBreakout3", "COPX.ARCA", length=350, extra_data=True),
    ]

    trader = Trader("BacktestExchange", advisors, "2021-01-01")

    try:
        trader.warm_up()
        trader.start()
    except KeyboardInterrupt:
        trader.stop()
    finally:
        trader.final_info()

    cprint(f"\nDone in {str(datetime.now() - dt)[:-7]}", attrs=['bold'])


if __name__ == "__main__":
    main()
