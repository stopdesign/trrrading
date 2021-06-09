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
from termcolor import cprint
from exchange import BaseExchange
from util import interval_dt, parse_quote
from settings import keys


api_keys = keys.demo
base = "https://api-demo.exante.eu"
account_id = "UEA7232.001"
ver = "3.0"

# Ключи для торговли
client_id = "40dd4b62-8296-46ff-9b6d-367ad9a35aed"
app_id = "72d39665-3477-4b48-aba6-b5688a0ab529"
shared_key = "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp"


class ExanteExchange(BaseExchange):
    def __init__(self, symbols: list, **kwargs):  # noqa
        super().__init__(symbols)

        self.symbols = symbols

        symbols_str = ",".join(self.symbols)

        self.url_trades = f"{base}/md/{ver}/feed/trades/{symbols_str}"
        self.url_quotes = f"{base}/md/{ver}/feed/{symbols_str}"
        self.url_orders = f"{base}/trade/{ver}/orders"

        self.fee_rate = Decimal("0.02")

        self.auth_headers = self.get_headers()

        self.cash = self.get_cash_value()

    def start_listen(self, on_event, loop=None):
        loop.create_task(self.metronom(on_event))
        loop.create_task(self.trade_stream(on_event))
        loop.create_task(self.quote_stream(on_event))

    def get_headers(self):
        iat = int(datetime.now().replace(tzinfo=timezone.utc).timestamp())
        exp = iat + int(timedelta(days=30).total_seconds())
        aud = ["ohlc", "feed", "orders", "summary", "accounts"]
        payload = {"iss": client_id, "sub": app_id, "iat": iat, "exp": exp, "aud": aud}
        token = jwt.encode(payload, shared_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def next_data_headers(self):
        global api_keys
        api_keys = api_keys[1:] + [api_keys[0]]
        key = api_keys[0]
        payload = {"iss": key[0], "sub": key[1], "aud": ["ohlc", "feed"]}
        token = jwt.encode(payload, key[2], algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

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
                if "timestamp" in interval and "bid" in interval and "ask" in interval:
                    quotes.append(interval)
            except JSONDecodeError as e:
                print("JSONDecodeError", line, data)
                raise e
        return quotes

    async def metronom(self, on_event):
        """
        В начале каждого интервала запускает обновление historical.
        """
        prev_dt = datetime(2000, 1, 1)
        while True:
            dt = datetime.utcnow()
            if dt.minute != prev_dt.minute:
                norm_dt = dt.replace(second=0, microsecond=0)
                # раз в минуту обновлять позиции
                self.get_positions()
                on_event("before_interval", norm_dt)
            await asyncio.sleep(0.5)
            prev_dt = dt

    async def trade_stream(self, on_event):
        """
        Обработка стрима сделок.
        """
        stream_headers = {"Accept": "application/x-json-stream"}
        headers = dict(self.auth_headers, **stream_headers)
        timeout = aiohttp.ClientTimeout(total=None, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.url_trades, headers=headers) as resp:
                async for data in resp.content.iter_any():
                    if trades := self.parse_trades(data):
                        # FIXME: переделать с поддержкой symbol
                        # trades = sorted(trades, key=lambda x: x["price"])
                        for trade in trades:
                            dt = interval_dt(trade)
                            symbol = trade["symbolId"]
                            on_event("trade", dt, symbol, parse_quote(trade))

    async def quote_stream(self, on_event):
        """
        Обработка стрима стакана.
        """
        stream_headers = {"Accept": "application/x-json-stream"}
        headers = dict(self.auth_headers, **stream_headers)
        timeout = aiohttp.ClientTimeout(total=None, sock_read=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(self.url_quotes, headers=headers) as resp:
                async for data in resp.content.iter_any():
                    if quotes := self.parse_quotes(data):
                        for quote in quotes:
                            dt = interval_dt(quote)
                            symbol = quote["symbolId"]
                            on_event("quote", dt, symbol, quote)

    def process_historical_data(self, on_event):
        """
        Используется для наполнения историческими данными.
        Запускается синхронно.
        """
        now = datetime.now().astimezone(timezone.utc)
        data = []
        for symbol in self.symbols:
            data += self.fetch_backtest_data(symbol, now, 60)
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
            "accountId": account_id,
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
        return (Decimal(ai["netAssetValue"]) / 100).quantize(Decimal("0.01"))

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
        url_account = f"{base}/md/{ver}/summary/{account_id}/USD"
        res = requests.get(url_account, headers=self.auth_headers)
        return res.json()

    def load_last_orders(self):
        url_orders = f"{base}/trade/{ver}/orders/active"
        res = requests.get(url_orders, headers=self.auth_headers)
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
        url_tick = f"{base}/md/3.0/ticks/{symbol}"
        while True:
            headers = self.next_data_headers()
            params = {"type": data_type, "from": timestamp, "size": size}
            res = requests.get(url_tick, params=params, headers=headers)
            if res.status_code == 200 and res.text:
                data = res.json()
                at_dt = interval_dt(data[0])
                print(f"Fetch {data_type} {symbol}, len: {len(data)}, dt: {at_dt}")
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

    def fetch_backtest_data(self, symbol, start_at, minutes):
        exchange = symbol.split(".")[1]
        exchange = exchange.replace("ARCA", "NYSE")
        dt_from = self.count_back_trading_minutes(exchange, start_at, minutes)

        # TODO: приделать сюда parse_trades и parse_quotes
        quotes = self.fetch_data(symbol, dt_from, "quotes")
        trades = self.fetch_data(symbol, dt_from, "trades")

        return sorted(quotes + trades, key=lambda x: x["timestamp"])
