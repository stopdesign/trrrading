import os
import sys
import logging
from datetime import datetime
from termcolor import cprint
from advisor import Advisor
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


def main() -> None:
    dt = datetime.now()

    advisors = [
        Advisor("ChannelBreakout3", "COPX.ARCA", length=350, padding=0.1),
        Advisor("ChannelBreakout3", "COPX.ARCA", length=450, padding=0.05),
        Advisor("ChannelBreakout3", "COPX.ARCA", length=550, padding=0.01),

        Advisor("ChannelBreakout3", "URA.ARCA", length=450, padding=0.01),
        Advisor("ChannelBreakout3", "URA.ARCA", length=520, padding=0.01),
        Advisor("ChannelBreakout3", "URA.ARCA", length=600, padding=0.02),
    ]

    trader = Trader("BacktestExchange", advisors, 10000, "2021-01-01")
    # trader = Trader("IBFakeExchange", advisors, 10000)

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
