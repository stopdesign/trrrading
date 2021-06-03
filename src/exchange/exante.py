import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from json import JSONDecodeError
from time import sleep
from typing import Callable, Optional

import aiohttp
import jwt
import requests
from termcolor import cprint

from exchange import BaseExchange
from strategy import Signal
from util import (
    print_order_info,
    print_trade_final_info, interval_dt,
)


base = "https://api-demo.exante.eu"
account_id = "UEA7232.001"
ver = "3.0"

client_id = "40dd4b62-8296-46ff-9b6d-367ad9a35aed"
app_id = "72d39665-3477-4b48-aba6-b5688a0ab529"
shared_key = "4BJ/niyJm3Mf84JzeN5LtVHIESc+azGp"


class ExanteExchange(BaseExchange):

    bid: list
    ask: list
    cash: Decimal
    quotes_updated_at: Optional[datetime]
    name: str = "exante"
    env: str = "demo"

    def __init__(
        self, on_trade: Callable, on_quote: Callable, on_interval: Callable, **params
    ):
        super().__init__(on_trade, on_quote, on_interval, **params)

        self.symbol = params.get("symbol")

        self.url_trades = f"{base}/md/{ver}/feed/trades/{self.symbol}"
        self.url_quotes = f"{base}/md/{ver}/feed/{self.symbol}"
        self.url_orders = f"{base}/trade/{ver}/orders"

        print(self.symbol)
        print()

        self.bid = []
        self.ask = []
        self.quotes_updated_at = None
        self.cash_initial = Decimal(10_000)
        self.cash = self.cash_initial
        self.fee_rate = Decimal("0.02")

        self.auth_headers = self.get_headers()

        self.load_account_info()

        # info
        self.position_open_cash = self.cash
        self.position_open_dt = None
        self.max_potential_cash = Decimal("-Infinity")
        self.max_drawdown = Decimal("-Infinity")

        self.local_max_potential_cash = Decimal("-Infinity")
        self.local_max_drawdown = Decimal("-Infinity")

        #
        self.trades = []

    def start_listen(self, loop=None):
        loop.create_task(self.trade_stream())
        loop.create_task(self.quote_stream())

    def get_headers(self):
        dt_from = datetime.now()
        dt_from = int(dt_from.replace(tzinfo=timezone.utc).timestamp())

        dt_exp = datetime.now() + timedelta(days=30)
        dt_exp = int(dt_exp.replace(tzinfo=timezone.utc).timestamp())

        permissions = ["ohlc", "feed", "orders", "summary", "accounts"]
        payload = {
            "iss": client_id,
            "sub": app_id,
            "iat": dt_from,
            "exp": dt_exp,
            "aud": permissions,
        }
        token = jwt.encode(payload, shared_key, algorithm="HS256")
        auth_headers = {
            "Authorization": f"Bearer {token}",
        }
        return auth_headers

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
        Распарсить сделки
        """
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
                # print(interval)
                if "timestamp" in interval and "bid" in interval and "ask" in interval:
                    return interval
            except JSONDecodeError as e:
                print("JSONDecodeError", line, data)
                raise e

    async def trade_stream(self):
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
                        trades = sorted(trades, key=lambda x: x["price"])
                        trade_min = trades[0]
                        trade_max = trades[-1]
                        self.update_stats()
                        self.on_trade(trade_min)
                        if trade_min["price"] != trade_max["price"]:
                            self.update_stats()
                            self.on_trade(trade_max)

    async def quote_stream(self):
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
                        ask = quotes["ask"][0]
                        bid = quotes["bid"][0]
                        self.ask = [{
                            "price": Decimal(ask["price"]),
                            "size": int(Decimal(ask["size"])),
                        }]
                        self.bid = [{
                            "price": Decimal(bid["price"]),
                            "size": int(Decimal(bid["size"])),
                        }]
                        self.quotes_updated_at = interval_dt(quotes)
                        self.on_quote(quotes)
                        self.update_stats()

    def create_order(self, side: str, size: int):
        """
        Открыть позицию/ордер на бирже.
        """
        cprint(f"TRADE {side}")
        data = {
            "accountId": account_id,
            "symbolId": self.symbol,
            "side": side,
            "quantity": str(size),
            "orderType": "market",
            "duration": "day",
            "clientTag": "OLOLO, 250, 111 {''} {\"asd\": 123}",
        }
        res = requests.post(self.url_orders, json=data, headers=self.auth_headers)

        if res.status_code > 201:
            print(res.text)
            raise Exception(res.status_code)

        res_json = res.json()[0]
        order_id = res_json['orderId']
        order_status = res_json['orderState']['status']

        print(order_id, order_status)
        while True:
            sleep(0.5)
            url = f"{self.url_orders}/{order_id}"
            res = requests.get(url, headers=self.auth_headers)
            res_json = res.json()
            order_id = res_json['orderId']
            order_status = res_json['orderState']['status']
            print(order_id, order_status)

            if order_status == "rejected":
                order_reason = res_json.get('reason')
                cprint(f"order_status: {order_status}, reason: {order_reason}", color="red")
                # print(json.dumps(res_json, indent=2, default=str))

            if order_status not in ["placing", "working"]:
                # print(json.dumps(res_json, indent=2, default=str))
                positions = res_json['orderState']["fills"]
                price, size = self.calc_av_price(positions)
                break

        return price, size

    def check_quote_age(self, dt):
        quote_age = (dt - self.quotes_updated_at).total_seconds()
        if quote_age > 300 or quote_age < 0:
            cprint(f"quote age: {quote_age}", color="cyan")
            return False
        else:
            cprint(f"quote age: {quote_age}", color="white")
            return True

    def update_stats(self):
        # если открыта позиция, посчитать гипотетическую прибыль / убыль
        if self.position:
            if self.position == "LONG":
                price = self.get_price("sell")
                profit = (price - self.position_open_price) * self.position_size
            elif self.position == "SHORT":
                price = self.get_price("buy")
                profit = (self.position_open_price - price) * self.position_size
            else:
                raise ValueError(f"Unknown position type: {self.position}")

            ###############################################
            # глобальные параметры для всей торговли

            position_open_value = self.position_size * self.position_open_price
            fee = self.fee_rate * self.position_size
            potential_cash = self.cash + position_open_value + profit - fee

            if potential_cash > self.max_potential_cash:
                self.max_potential_cash = potential_cash

            drawdown = self.max_potential_cash - potential_cash
            drawdown_rel = drawdown / position_open_value * 100
            self.max_drawdown = max(self.max_drawdown, drawdown_rel)

            ###############################################
            # локальные параметры для данной сделки

            if potential_cash > self.local_max_potential_cash:
                self.local_max_potential_cash = potential_cash

            local_drawdown = self.local_max_potential_cash - potential_cash
            local_drawdown_rel = local_drawdown / position_open_value * 100
            self.local_max_drawdown = max(self.local_max_drawdown, local_drawdown_rel)

    def get_price(self, side: str) -> Decimal:
        if side == "sell":
            price = self.bid[0]["price"]
        elif side == "buy":
            price = self.ask[0]["price"]
        else:
            raise ValueError(f"Unknown side: {side}")
        return price

    def open_position(self, dt: datetime, signal: Signal, size: int):
        if not self.check_quote_age(dt):
            return

        size = 10
        if signal == Signal.LONG:
            # size = self.get_max_amount(self.cash, "buy")
            price, _ = self.create_order("buy", size)
        elif signal == Signal.SHORT:
            # size = self.get_max_amount(self.cash, "sell")
            price, _ = self.create_order("sell", size)
        else:
            raise ValueError(f"Unknown signal: {signal}")

        if not price:
            cprint("error create_order")
            print()
            return

        self.position_open_cash = self.cash
        self.cash -= price * size + self.fee_rate * size

        print_order_info(dt, signal.value, price, size, self.cash)

        self.position = signal.value
        self.position_size = size
        self.position_open_price = price
        self.position_open_dt = dt

    def close_position(self, dt: datetime):
        if not self.check_quote_age(dt):
            return

        if self.position == "LONG":
            price, size = self.create_order("sell", self.position_size)
            profit = (price - self.position_open_price) * self.position_size
        elif self.position == "SHORT":
            price, size = self.create_order("buy", self.position_size)
            profit = (self.position_open_price - price) * self.position_size
        else:
            raise ValueError(f"Unknown position type: {self.position}")

        if not price:
            cprint("error create_order")
            print()
            return

        position_open_value = self.position_size * self.position_open_price
        profit_rel = profit / position_open_value * 100
        fee = self.fee_rate * self.position_size
        self.cash += position_open_value + profit - fee

        print_order_info(dt, "CLOSE", price, 0, self.cash)
        print()

        # TODO: вынести position(s) в отдельный класс,
        # TODO: перенести в него все параметры о сделке
        print_trade_final_info(
            dt,
            self.position,
            self.position_open_dt,
            profit,
            profit_rel,
            self.cash,
            self.cash_initial,
            self.max_potential_cash,
            self.max_drawdown,
            self.local_max_potential_cash,
            self.local_max_drawdown,
        )
        # print()

        self.position_open_cash = None
        self.position = None
        self.position_size = 0
        self.position_open_price = None

        self.local_max_potential_cash = Decimal("-Infinity")
        self.local_max_drawdown = Decimal("-Infinity")

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

        av_price = sum_price / total_quantity

        return av_price, total_quantity

    def load_account_info(self):
        url_account = f"{base}/md/{ver}/summary/{account_id}/EUR"

        res = requests.get(url_account, headers=self.auth_headers)
        print(json.dumps(res.json(), indent=2, default=str))

        print('\n------\n')

        url_orders = f"{base}/trade/{ver}/orders/active"

        res = requests.get(url_orders, headers=self.auth_headers)
        print(json.dumps(res.json(), indent=2, default=str))

        import sys
        sys.exit(1)
