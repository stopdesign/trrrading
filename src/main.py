import asyncio
import signal
import time
from datetime import datetime
from termcolor import cprint
from trader import Trader
from exchange import BacktestExchange, ExanteExchange
from strategy import ChannelBreakout


async def stop(signal, loop):
    """
    Хуй знает, что тут происходит.
    """
    print()
    cprint(f"Received exit signal {signal.name}...", "red")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    print("Cancelling tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


def main() -> None:
    print()

    dt = datetime.now()
    loop = asyncio.get_event_loop()

    # Убиватор тасков
    for sig in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(stop(sig, loop)))

    traders = [
        # Trader(BacktestExchange, ChannelBreakout(length=100), symbol="LIT.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=200), symbol="LIT.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=300), symbol="LIT.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=400), symbol="LIT.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=500), symbol="LIT.ARCA"),

        # Trader(BacktestExchange, ChannelBreakout(length=120), symbol="COPX.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=180), symbol="COPX.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=350), symbol="COPX.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=480), symbol="COPX.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=120), symbol="URA.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=190), symbol="URA.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=260), symbol="URA.ARCA"),
        # Trader(BacktestExchange, ChannelBreakout(length=300), symbol="URA.ARCA"),

        Trader(ExanteExchange, ChannelBreakout(length=2, min_length=1), symbol="COPX.ARCA"),
        Trader(ExanteExchange, ChannelBreakout(length=2, min_length=1), symbol="URA.ARCA"),
    ]
    """
    
    
    """





    try:
        for trader in traders:
            trader.start(loop)
        if traders[0].exchange.__class__ is ExanteExchange:
            loop.run_forever()
    except KeyboardInterrupt:
        print("Process interrupted")
    finally:
        loop.close()

    all_keys = []
    for trader in traders:
        all_keys += trader.info.keys()
    all_keys = list(set(all_keys))
    all_keys.sort()

    cur_val = [0] * len(traders)
    cur_max = [0] * len(traders)
    cur_dd = [0] * len(traders)
    sum_max = 0
    sum_dd = 0
    for key in all_keys:
        print(key, end="\t")
        for i, trader in enumerate(traders):
            if info := trader.info.get(key):
                cur_val[i] = int(info["cash"])
            cur_max[i] = max(cur_max[i], cur_val[i])
            if cur_max[i]:
                cur_dd[i] = "%0.2f" % ((cur_max[i] - cur_val[i]) / cur_max[i] * 100)
            else:
                cur_dd[i] = 0

        sum_val = int(sum(cur_val))
        sum_max = max(sum_val, sum_max)
        sum_dd = "%0.2f" % ((sum_max - sum_val) / sum_max * 100)

        sum_all = str(int(sum(cur_val) / len(traders)))
        print(
            "\t".join(map(str, cur_val)) +
            "\t" +
            f"{sum_all}" +
            "\t\t" +
            "\t".join(map(str, cur_dd)) +
            f"\t\t{sum_dd}"
        )

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=['bold'])


def main_2():

    # инициализировать инстанс биржи
    ExanteExchange()

    # TradingManager
    #


if __name__ == "__main__":
    main()
