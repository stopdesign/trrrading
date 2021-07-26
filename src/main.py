from datetime import datetime
from termcolor import cprint
from advisor import Advisor
from trader import Trader

import sys, os
sys.path.append(os.path.abspath("."))


def main() -> None:
    dt = datetime.now()

    advisors = [
        Advisor("Dummy", "COPX.ARCA", interval=3 * 60 * 60),
        Advisor("ChannelBreakout2", "COPX.ARCA", length=350, extra_data=False),
    ]

    dt_start = datetime(2021, 3, 1)

    trader = Trader(advisors, dt_start)

    try:
        trader.start()
    except KeyboardInterrupt:
        trader.stop()
    finally:
        trader.final_info()

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=['bold'])


if __name__ == "__main__":
    main()
