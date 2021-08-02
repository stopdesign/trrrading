import os
import sys
import logging
from datetime import datetime
from termcolor import cprint
from advisor import Advisor
from trader import Trader


sys.path.append(os.path.abspath("."))


root = logging.getLogger()
root.setLevel(logging.INFO)
h = logging.StreamHandler(sys.stdout)
# h.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(message)s'))
root.addHandler(h)

fmt = logging.Formatter('\033[0;35m%(name)s - %(levelname)s - %(message)s\033[0m')
h = logging.StreamHandler(sys.stdout)
h.setFormatter(fmt)

l1 = logging.getLogger('ib_insync.ib')
l1.setLevel(logging.INFO)
l1.addHandler(h)
l1.propagate = False

l2 = logging.getLogger('ib_insync.client')
l2.setLevel(logging.INFO)
l2.addHandler(h)
l2.propagate = False

l3 = logging.getLogger('ib_insync.wrapper')
l3.setLevel(logging.WARNING)
l3.addHandler(h)
l3.propagate = False


def main() -> None:
    dt = datetime.now()

    advisors = [
        Advisor(
            "ChannelBreakout3",
            "SPY.ARCA",
            length=2,
            extra_data=True,
            extra_trade=True,
        ),
    ]

    trader = Trader("IBFakeExchange", advisors, "2021-05-01")

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
