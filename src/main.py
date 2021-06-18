import asyncio
import signal
from datetime import datetime
from termcolor import cprint
from trader import Trader

import sys, os
sys.path.append(os.path.abspath("."))

import settings


async def stop(signal, loop):
    """
    Хуй знает, что тут происходит.
    """
    print()
    cprint(f"Received exit signal {signal.name}...", "red")

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        cprint(f"Cancel task: {task.get_coro()}", "yellow")
        task.cancel()

    cprint("Gathering tasks...", "red")
    await asyncio.gather(*tasks, return_exceptions=True)

    loop.stop()


def main() -> None:
    dt = datetime.now()
    loop = asyncio.get_event_loop()

    # Убиватор тасков
    for s in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(s, lambda: asyncio.create_task(stop(s, loop)))

    trader = Trader()

    trader.start(loop)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("Process interrupted")
    finally:
        trader.stop(loop)
        trader.final_info()
        loop.close()

    total_time = (datetime.now() - dt).total_seconds()
    cprint(f"\nDone in {total_time:0.2f} s", attrs=['bold'])


if __name__ == "__main__":
    main()
