import asyncio
import signal
from datetime import datetime

import aiohttp
import jwt
from aiohttp import ServerTimeoutError, ClientConnectorError
from termcolor import cprint, colored

import sys, os
sys.path.append(os.path.abspath(".."))

from settings import keys
from main import stop


env = "demo"
api_keys = getattr(keys, env)[0]


base = f"https://api-{env}.exante.eu"
ver = "3.0"


class TestExchange:

    def __init__(self):
        self.finished = False
        self.iss, self.sub, self.shared_key = api_keys

        # symbols_str = "SPY.ARCA,DIA.ARCA"
        symbols_str = "COPX.ARCA"

        self.prev_now = datetime.utcnow()

        self.url_trades = f"{base}/md/{ver}/feed/trades/{symbols_str}"
        self.url_quotes = f"{base}/md/{ver}/feed/{symbols_str}"

    @property
    def auth_headers(self):
        payload = {"iss": self.iss, "sub": self.sub, "aud": ["feed"]}
        token = jwt.encode(payload, self.shared_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    @property
    def timeout(self):
        return aiohttp.ClientTimeout(total=None, sock_read=30)

    @property
    def headers(self):
        stream_headers = {"Accept": "application/x-json-stream"}
        return dict(self.auth_headers, **stream_headers)

    async def data_stream(self, url):
        min_delay = 0.5
        max_delay = 30
        delay = min_delay
        while not self.finished:
            cprint("Start listening trade stream", "blue")
            async with aiohttp.ClientSession(timeout=self.timeout) as cs:
                try:
                    async with cs.get(url, headers=self.headers) as resp:
                        async for data in resp.content.iter_any():
                            await self.process_data("Event", data)
                            delay = min_delay  # reset the delay
                except ServerTimeoutError as e:
                    cprint(e, "yellow")
                except ClientConnectorError as e:
                    cprint(e, "red")
                except Exception as e:
                    cprint(e, "red")
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 2)  # exponential delay

    def start(self, loop):
        loop.create_task(self.data_stream(self.url_quotes))

    def stop(self, loop):
        pass

    async def process_data(self, stream, data):
        now = datetime.utcnow()
        diff_sec = (now - self.prev_now).total_seconds()
        data = data.decode().replace("\\n", "\n").strip()[:50]
        stream_tag = colored(f" {stream} ", "grey", attrs=["reverse"])
        print(f"{stream_tag} {now:%H:%M:%S %Z} {diff_sec:0.1f} {data}")
        self.prev_now = now


def main():
    loop = asyncio.get_event_loop()

    # Убиватор тасков
    for s in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(s, lambda: asyncio.create_task(stop(s, loop)))

    te = TestExchange()
    te.start(loop)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("Process interrupted")
    finally:
        te.stop(loop)
        loop.close()


if __name__ == "__main__":
    main()
