import asyncio
import json
import aiohttp
import jwt
import requests
import pandas_market_calendars as mcal
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from json import JSONDecodeError
from time import sleep
from aiohttp import ServerTimeoutError, ClientConnectorError
from termcolor import cprint
from exchange import BaseExchange
from util import interval_dt, parse_quote
from settings import (
    DATA_API_KEYS,
    BASE_URL_DATA,
    BASE_URL_TRADE,
    ACCOUNT_ID,
    CLIENT_ID,
    APP_ID,
    SHARED_KEY,
)


class ExanteExchange(BaseExchange):
    def __init__(self, symbols: list, **kwargs):  # noqa
        super().__init__(symbols)

        self.symbols = symbols
        symbols_str = ",".join(self.symbols)

        self.data_api_keys = DATA_API_KEYS

        # data urls
        self.url_trades = f"{BASE_URL_DATA}/md/3.0/feed/trades/{symbols_str}"
        self.url_quotes = f"{BASE_URL_DATA}/md/3.0/feed/{symbols_str}"
        self.url_ticks = f"{BASE_URL_DATA}/md/3.0/ticks"

        # trade urls
        self.url_orders = f"{BASE_URL_TRADE}/trade/3.0/orders"
        self.url_account = f"{BASE_URL_TRADE}/md/3.0/summary/{ACCOUNT_ID}/USD"

        # self.url_trades = "http://0.0.0.0:8080/trades/"

        self.fee_rate = Decimal("0.02")

        self.cash = self.get_cash_value()

    def start_listen(self, on_event, loop=None):
        task = asyncio.to_thread(self.healthcheck_loop)
        asyncio.gather(task, return_exceptions=True)
        loop.create_task(self.metronom(on_event))
        loop.create_task(self.trade_stream(on_event))
        loop.create_task(self.quote_stream(on_event))

    @property
    def auth_headers(self):
        iat = int(datetime.now().replace(tzinfo=timezone.utc).timestamp())
        exp = iat + int(timedelta(days=30).total_seconds())
        aud = ["ohlc", "feed", "orders", "summary", "accounts"]
        payload = {"iss": CLIENT_ID, "sub": APP_ID, "iat": iat, "exp": exp, "aud": aud}
        token = jwt.encode(payload, SHARED_KEY, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    @property
    def stream_headers(self):
        stream_headers = {"Accept": "application/x-json-stream"}
        return dict(self.data_headers, **stream_headers)

    @property
    def data_headers(self):
        # Ротация ключей
        self.data_api_keys = self.data_api_keys[1:] + [self.data_api_keys[0]]
        key = self.data_api_keys[0]
        aud = ["ohlc", "feed", "summary", "accounts"]
        payload = {"iss": key[0], "sub": key[1], "aud": aud}
        token = jwt.encode(payload, key[2], algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    @property
    def timeout(self):
        return aiohttp.ClientTimeout(total=None, sock_read=30)

    def parse_trades(self, data):
        """
        Распарсить сделки
        """
        trades = []
        data = data.decode().strip()
        for line in data.split("\n"):
            if not line.strip():
                continue
            try:
                interval = json.loads(line)
                if "timestamp" in interval and "price" in interval:
                    trades.append(interval)
            except JSONDecodeError as e:
                print("JSONDecodeError", line, data)
                raise e
        return trades

    def parse_quotes(self, data):
        """
        Распарсить quotes
        """
        quotes = []
        data = data.decode().strip()
        for line in data.split("\n"):
            if not line.strip():
                continue
            try:
                interval = json.loads(line)
                # {
                #   'timestamp': 1622584805370,
                #   'symbolId': 'COPX.ARCA',
                #   'bid': [{'price': '41.89', 'size': '100.0'}],
                #   'ask': [{'price': '42.47', 'size': '500.0'}],
                # }
                if "timestamp" in interval and "ask" in interval:
                    quotes.append(interval)
            except JSONDecodeError as e:
                print("JSONDecodeError", line, data)
                raise e
        return quotes

    def healthcheck_loop(self):
        interval = timedelta(seconds=5)
        prev_dt = datetime.utcnow()
        while not self.finished:
            if datetime.utcnow() - prev_dt > interval:
                self.do_healthcheck()
                prev_dt = datetime.utcnow()
            sleep(0.5)  # sleep маленький, чтобы цикл не зависал

    def do_healthcheck(self):
        """
        Проверить, как давно происходили разные события.
        """
        self.check_event_delay("healthcheck", 10)
        self.check_event_delay("trade_heartbeat", 60)
        self.check_event_delay("quote_heartbeat", 60)
        self.check_event_delay("trade", 3600)
        self.check_event_delay("quote", 3600)
        self.last_event["healthcheck"] = datetime.utcnow()

    def check_event_delay(self, event_name, max_delay):
        """
        Проверить, не отстало ли событие от расписания.
        Отправить алерт, если что.
        """
        last_event_at = self.last_event.get(event_name)
        if not last_event_at:
            return
        timeout = timedelta(seconds=max_delay)
        now = datetime.utcnow()
        actual_delay = now - last_event_at
        if actual_delay > timeout:
            cprint(
                f"{now}: Event {event_name} is late: {last_event_at}, "
                f"{actual_delay.total_seconds():0.0f} "
                f"> {max_delay}",
                "red",
            )

    async def metronom(self, on_event):
        """
        В начале каждого интервала запускает обновление historical.
        """
        prev_dt = datetime(2000, 1, 1)
        while not self.finished:
            dt = datetime.utcnow()
            if dt.minute != prev_dt.minute:
                norm_dt = dt.replace(second=0, microsecond=0)
                # раз в минуту обновлять позиции
                self.get_positions()
                on_event("before_interval", norm_dt)
            self.last_event["metronom"] = datetime.utcnow()
            await asyncio.sleep(1)
            prev_dt = dt

    async def data_stream(self, url, processor, on_event):
        """
        Подписка на стрим биржи.
        """
        min_delay = 0.5
        max_delay = 30
        delay = min_delay
        while not self.finished:
            cprint(f"Start listening {url}", "blue")
            async with aiohttp.ClientSession(timeout=self.timeout) as cs:
                try:
                    headers = self.stream_headers
                    async with cs.get(url, headers=headers) as resp:
                        async for data in resp.content.iter_any():
                            await processor(data, on_event)
                            delay = min_delay  # reset the delay
                except ServerTimeoutError as e:
                    cprint(e, "yellow")
                except ClientConnectorError as e:
                    cprint(e, "red")
                except Exception as e:
                    cprint(e, "red")
            await asyncio.sleep(delay)
            delay = min(max_delay, delay * 2)  # exponential delay

    async def quote_stream(self, on_event):
        return await self.data_stream(self.url_quotes, self.on_quote, on_event)

    async def trade_stream(self, on_event):
        return await self.data_stream(self.url_trades, self.on_trade, on_event)

    async def on_trade(self, data, on_event):
        """
        Обработка события trade_stream.
        """
        self.last_event["trade_heartbeat"] = datetime.utcnow()
        if trades := self.parse_trades(data):
            # TODO: сделать группировку trades с поддержкой symbol
            for trade in trades:
                dt = interval_dt(trade)
                symbol = trade["symbolId"]
                if on_event("trade", dt, symbol, parse_quote(trade)):
                    self.last_event["trade"] = datetime.utcnow()

    async def on_quote(self, data, on_event):
        """
        Обработка события quote_stream.
        """
        self.last_event["quote_heartbeat"] = datetime.utcnow()
        if quotes := self.parse_quotes(data):
            for quote in quotes:
                dt = interval_dt(quote)
                symbol = quote["symbolId"]
                if on_event("quote", dt, symbol, quote):
                    self.last_event["quote"] = datetime.utcnow()

    def process_historical_data(self, on_event):
        """
        Используется для наполнения историческими данными.
        Запускается синхронно.
        """
        now = datetime.now().astimezone(timezone.utc)
        data = []
        for symbol in self.symbols:
            data += self.get_past_data(symbol, now, 60 * 25)  # подсчитать, сколько надо
        data = sorted(data, key=lambda x: x["timestamp"])

        for event in data:
            symbol = event.get("symbolId")

            if not symbol or "timestamp" not in event:
                continue

            dt = interval_dt(event)

            if "price" in event:
                on_event("historical_trade", dt, symbol, parse_quote(event))

            if "ask" in event:
                ask = list(map(parse_quote, event["ask"]))
                bid = list(map(parse_quote, event["bid"]))
                on_event("historical_quote", dt, symbol, {"ask": ask, "bid": bid})

    def trade(self, side: str, size: int, symbol: str):
        """
        Открыть позицию/ордер на бирже.
        """
        cprint(f"TRADE: {side} {symbol} {size}", color="cyan")
        data = {
            "accountId": ACCOUNT_ID,
            "symbolId": symbol,
            "side": side,
            "quantity": str(size),
            "orderType": "market",
            "duration": "day",
            "clientTag": "BOT",
        }

        res = requests.post(self.url_orders, json=data, headers=self.auth_headers)

        if res.status_code > 201:
            cprint(res.text, "red")
            raise Exception(res.status_code)

        res_json = res.json()[0]
        order_id = res_json["orderId"]
        order_status = res_json["orderState"]["status"]
        cprint(f"{order_id}, {order_status}", "white")

        order_status_url = f"{self.url_orders}/{order_id}"

        while True:
            sleep(0.5)
            res = requests.get(order_status_url, headers=self.auth_headers)
            res_json = res.json()
            order_id = res_json["orderId"]
            order_status = res_json["orderState"]["status"]
            cprint(f"{order_id}, {order_status}", "white")

            if order_status == "rejected":
                order_reason = res_json["orderState"].get("reason")
                cprint(f"{order_status}, {order_reason}", color="red")
                return None, None

            if order_status not in ["placing", "working", "pending"]:
                positions = res_json["orderState"]["fills"]
                last_update = res_json["orderState"]["lastUpdate"]
                price, size = self.calc_av_price(positions)
                cprint(
                    f"TRADE DONE: {last_update}, price: {price:0.4f}, size: {size}",
                    color="cyan",
                )
                sleep(1)
                break

        return price, size

    def calc_av_price(self, fills):
        """
        [{
            "quantity": "4E+2",
            "price": "42",
            "position": 2,
            "timestamp": "2021-06-01T19:33:22.534Z"
        }]
        """
        sum_price = Decimal(0)
        total_quantity = 0

        for position in fills:
            quantity = int(Decimal(position["quantity"]))
            price = Decimal(position["price"])
            total_quantity += quantity
            sum_price += price * quantity

        if total_quantity:
            av_price = sum_price / total_quantity
            return av_price, total_quantity
        else:
            return None, 0

    def get_cash_value(self):
        ai = self.load_account_info()
        return Decimal(ai["netAssetValue"])

    def get_positions(self):
        ai = self.load_account_info()
        res = {}
        for position in ai["positions"]:
            amount = Decimal(position["quantity"])
            if amount:
                price = Decimal(position["averagePrice"])
            else:
                price = self.empty_position["price"]
            res[position["symbolId"]] = {"amount": amount, "price": price}
        # Кеширование позиций
        self.positions = res
        return res

    def load_account_info(self):
        # cprint("load_account_info", "yellow")
        res = requests.get(self.url_account, headers=self.auth_headers)
        return res.json()

    def load_last_orders(self):
        cprint("load_last_orders", "yellow")
        url = f"{self.url_orders}/active"
        res = requests.get(url, headers=self.auth_headers)
        return res.json()

    def count_back_trading_minutes(self, exchange, dt, minutes):
        """
        Отсчитывает minutes минут назад от dt
        с учетом рабочего расписания биржи.
        """
        cal = mcal.get_calendar(exchange)
        schedule = cal.schedule(start_date=dt - timedelta(days=20), end_date=dt)
        all_minutes = 0
        for day, t in sorted(schedule.T.to_dict("list").items(), reverse=True):
            t0, t1 = min(dt, t[0].to_pydatetime()), min(dt, t[1].to_pydatetime())
            day_minutes = (t1 - t0).total_seconds() // 60
            if day_minutes and day_minutes + all_minutes >= minutes:
                return t1 - timedelta(minutes=minutes - all_minutes)
            all_minutes += day_minutes

    def fetch_data(self, symbol, dt, data_type):
        all_data = []
        size = 5000
        timestamp = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        url = f"{self.url_ticks}/{symbol}"
        while True:
            params = {"type": data_type, "from": timestamp, "size": size}
            res = requests.get(url, params=params, headers=self.data_headers)
            if res.status_code == 200 and len(res.text) > 10:
                data = res.json()
                dt1 = interval_dt(data[-1])
                dt2 = interval_dt(data[0])
                cprint(f"Fetch {data_type} {symbol}, [{dt1}, {dt2}], {len(data)}")
                all_data += data
                if len(data) < size:
                    break
                timestamp = data[0]["timestamp"] + 1
                sleep(0.5)
            elif res.status_code == 429:
                print("API limits...")
                sleep(3)
            else:
                raise Exception(f"Bad response: {res.text}")
        # Удаление повторов
        all_data = [json.loads(t) for t in {json.dumps(d) for d in all_data}]
        return all_data

    def get_past_data(self, symbol, before_dt, minutes):
        """
        Получить исторические данные.
        """
        exchange = symbol.split(".")[1]
        exchange = exchange.replace("ARCA", "NYSE")
        dt_from = self.count_back_trading_minutes(exchange, before_dt, minutes)

        cprint(f"Get past {symbol}, [{dt_from}, {before_dt}]")

        # TODO: приделать сюда parse_trades и parse_quotes
        quotes = self.fetch_data(symbol, dt_from, "quotes")
        trades = self.fetch_data(symbol, dt_from, "trades")

        return sorted(quotes + trades, key=lambda x: x["timestamp"])
