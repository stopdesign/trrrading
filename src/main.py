import os
import sys
import logging
from datetime import datetime
from termcolor import cprint
from advisor import Advisor
from trader import Trader


sys.path.append(os.path.abspath("."))


# Чтобы логи валились в stdout
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(logging.StreamHandler(sys.stdout))


def main() -> None:
    dt = datetime.now()

    advisors = [
        Advisor(
            "ChannelBreakout3",
            "COPX.ARCA",
            length=5,
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
