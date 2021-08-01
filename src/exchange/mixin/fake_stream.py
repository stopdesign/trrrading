import asyncio
import aiohttp
from termcolor import cprint


class FakeStream:
    finished = None

    async def fake_stream(self, url):
        """
        Подписка на стрим фейковой биржи.
        """
        min_delay = 0.5
        max_delay = 30
        delay = min_delay
        timeout = aiohttp.ClientTimeout(total=None, sock_read=300)
        while not self.finished:
            cprint(f"Fake stream at {url}", "blue")
            async with aiohttp.ClientSession(timeout=timeout) as cs:
                try:
                    async with cs.get(url) as resp:
                        async for data in resp.content.iter_any():
                            await self.fake_stream_event(data)
                            delay = min_delay  # reset the delay
                except aiohttp.ServerTimeoutError as e:
                    cprint(e, "yellow")
                except aiohttp.ClientConnectorError as e:
                    cprint(e, "red")
                except Exception as e:
                    cprint(e, "red")
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 2)  # exponential delay

    async def fake_stream_event(self, data):
        raise NotImplementedError
