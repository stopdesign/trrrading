import json
import aiohttp
import jwt
import requests
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from json import JSONDecodeError
from time import sleep
from termcolor import cprint
from exchange import BaseExchange
from util import interval_dt, parse_quote


base = "https://api-demo.exante.eu"
account_id = "UEA7232.001"
ver = "3.0"

client_id = "40dd4b62-8296-46ff-9b6d-367ad9a35aed"
app_id = "72d39665-3477-4b48-aba6-b5688a0ab529"
shared_key = "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp"

keys = [
    # Demo
    [
        "40dd4b62-8296-46ff-9b6d-367ad9a35aed",
        "72d39665-3477-4b48-aba6-b5688a0ab529",
        "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp",
    ],
    [
        "8bae08b2-5db3-4c76-a10c-4ef583fe4c6e",
        "6d4b874c-7ad8-41a9-a519-dbf80e7f47d8",
        "fqaQ35TT9HXy23skVuNoSg+ulE7RF1zv",
    ],
    [
        "bf849eea-2d2b-4eb9-8ee3-33829a5ab389",
        "343115e2-002f-4b8b-9b49-f7246599c7e2",
        "jetk63nW4SRrF5dC+fkkBVo5N/eiD3VW",
    ],
    [
        "3f29df5b-a046-4f10-9a05-3ad58633b79e",
        "6841ae47-a7f0-4366-affe-a6df0e5c189f",
        "4fEOjBkYVqEotIsC/Zw1lQUPHJ/WbEhp",
    ],
    [
        "90fb5b9b-d701-4c08-9e1b-aebbe3d5f8f0",
        "c26618e5-d8ad-4b1e-a602-57fd2ff61e87",
        "/2gXlIv2sr/wgHVQGJUNMukbeTrHh1ry",
    ],
]


class ExanteExchange(BaseExchange):
    def __init__(self, symbols: list, **kwargs):
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
        global keys
        keys = keys[1:] + [keys[0]]
        key = keys[0]
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
                            ask = list(map(parse_quote, quote["ask"]))
                            bid = list(map(parse_quote, quote["bid"]))
                            self.quotes[symbol] = {"ask": ask, "bid": bid, "dt": dt}
                            on_event("quote", dt, symbol, {"ask": ask, "bid": bid})

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
                    f"ORDER DONE: {last_update}, price: {price}, size: {size}",
                    color="cyan",
                )
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
            res[position["symbolId"]] = {
                "amount": Decimal(position["quantity"]),
                "price": Decimal(position["averagePrice"]),
            }
        return res

    def load_account_info(self):
        url_account = f"{base}/md/{ver}/summary/{account_id}/USD"
        res = requests.get(url_account, headers=self.auth_headers)
        return res.json()

    def load_last_orders(self):
        url_orders = f"{base}/trade/{ver}/orders/active"
        res = requests.get(url_orders, headers=self.auth_headers)
        return res.json()

    def fetch_ohlc_data(self, symbol, data_type, from_dt, interval_size):
        url_ohlc = f"{base}/md/3.0/ohlc/{symbol}/{interval_size}"

        from_dt = int(from_dt.replace(tzinfo=timezone.utc).timestamp()) * 1000

        all_data = []
        while True:
            params = {
                "type": data_type,
                "from": from_dt,
                "size": 5000,
            }
            headers = self.next_data_headers()
            res = requests.get(url_ohlc, params=params, headers=headers)
            sleep(1)

            if res.status_code == 200:
                all_data += res.json()
                break

            elif res.status_code == 429:
                sleep(10)

            else:
                print(res.status_code)
                print(res.text)
                raise Exception("fetch_ohlc_data error")

        # убрать повторы
        all_data = [json.loads(t) for t in {json.dumps(d) for d in all_data}]

        # сортировать
        all_data = sorted(all_data, key=lambda x: x["timestamp"])

        return all_data

    def fetch_tick_data(self, symbol, data_type, from_dt):
        url_tick = f"{base}/md/3.0/ticks/{symbol}"

        from_dt = int(from_dt.replace(tzinfo=timezone.utc).timestamp()) * 1000
        to_dt = int(datetime.utcnow().timestamp()) * 1000

        all_data = []
        while True:
            params = {
                "type": data_type,
                "to": to_dt,
                "size": 5000,
            }
            res = requests.get(url_tick, params=params, headers=self.auth_headers)

            if res.status_code == 200:
                data = res.json()
                if not data:
                    # print("EMPTY RESPONSE")
                    break

                to_dt = data[-1]["timestamp"]

                # print(datetime.now(), len(data), interval_dt(data[0]))

                all_data += data

                if len(data) <= 50:
                    # print("< 50")
                    break

                if data[-1]["timestamp"] < from_dt:
                    # print("ALL DONE")
                    break

                sleep(60)

            elif res.status_code == 429:
                # print("429")
                sleep(30)

            else:
                print(res.status_code)
                print(res.text)
                raise Exception("fetch_tick_data error")

        # убрать повторы
        all_data = [json.loads(t) for t in {json.dumps(d) for d in all_data}]

        # сортировать
        all_data = sorted(all_data, key=lambda x: x["timestamp"])

        return all_data

    @property
    def net_value(self):
        """
        Суммарное количество бабла депозита: кэш плюс стоимость активов.
        """
        total_value = self.cash
        for symbol, position in self.positions.items():
            if position["amount"] > 0:
                price = self.get_price(symbol, "sell")
                total_value += position["amount"] * (price - position["price"])
                total_value -= self.fee_rate * position["amount"]
            if position["amount"] < 0:
                price = self.get_price(symbol, "buy")
                total_value += position["amount"] * (position["price"] - price)
                total_value -= self.fee_rate * position["amount"]
        return total_value
