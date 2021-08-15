import asyncio
import aiohttp
from termcolor import cprint


class FakeStream:
    finished = None

    async def fake_stream(self, url, params):
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
                    async with cs.get(url, params=params) as resp:
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

    # def start_listen(self):
    #     # Фейковая биржа
    #     if self.contracts:
    #         contract = self.contracts[0]
    #         symbol = f"{contract.symbol}.{contract.exchange}"
    #         symbol = symbol.replace(".SMART", ".ARCA")
    #         params = {
    #             "symbol": symbol,
    #             "price": "438.50",
    #         }
    #         self.loop.create_task(self.fake_stream(self.fake_stream_url, params))

    # async def fake_stream_event(self, data):
    #     data = json.loads(data.decode())
    #
    #     dt = datetime.utcnow().replace(microsecond=0)
    #     self.dt_last = dt
    #
    #     symbol = data["symbolId"]
    #
    #     price = float(data["price"])
    #     volume = int(float(data["size"]))
    #
    #     quote = BidAsk(bid=price - 0.02, ask=price + 0.02)
    #     self.on_event("quote", dt, symbol, quote)
    #
    #     trade = Trade(price=price, volume=volume)
    #     self.on_event("trade", dt, symbol, trade)
    #
    #     bar = Bar.from_fake_trade(
    #         ticker=symbol,
    #         date=dt,
    #         price=price,
    #         volume=volume,
    #     )
    #     self.on_event("bar", dt, symbol, bar)
