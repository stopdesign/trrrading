import asyncio
import json
import random
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import redis
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from main.models import Account, Position, Trade, Contract
from main.views import get_orders
from main.views_pnl import PerformanceReport


"""
        a = Account.objects.get(pk=account_id)

        self.now = datetime.now().replace(microsecond=0).astimezone(ZoneInfo("UTC"))

        # Calculate the start date by going back to the most recent Sunday
        prev_sun = self.now - timedelta(days=self.now.weekday() + 1)
        prev_sun = prev_sun.replace(hour=0, minute=0, second=0, microsecond=0)

        # Начало первой недели отчета
        dt_1 = prev_sun - timedelta(weeks=RANGE)

        # Запас на праздники и UTC
        dt_0 = dt_1 - timedelta(days=self.holiday_gap_days)

        # Позиции данного аккаунта сейчас по всем контрактам
        positions = Position.objects.filter(account=a).prefetch_related("contract")

        # Одним запросом достаю сделки данного аккаунта за весь период
        trades = Trade.objects.order_by("time").prefetch_related("order__contract")
        trades = trades.filter(account=a, time__gt=dt_1)

        self.trades_by_sid = defaultdict(list)
        for trade in trades:
            self.trades_by_sid[trade.order.contract.sid].append(trade)

        # Контракты, которые есть в сделках или позициях
        contracts = {t.order.contract for t in trades}
        contracts.update({p.contract for p in positions})
        self.contracts = contracts

        # Positions from contracts with trades
        self.positions_by_sid = {c.sid: 0 for c in self.contracts}

        # Current positions from DB
        self.positions_by_sid.update({p.contract.sid: p.amount or 0 for p in positions})
"""

def get_positions(account_id):
    res = []

    RANGE = 15

    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    too_old = utc_now - timedelta(days=1)

    self_now = datetime.now().replace(microsecond=0).astimezone(timezone.utc)

    # Calculate the start date by going back to the most recent Sunday
    prev_sun = self_now - timedelta(days=self_now.weekday() + 1)
    prev_sun = prev_sun.replace(hour=0, minute=0, second=0, microsecond=0)

    # Начало первой недели отчета
    dt_1 = prev_sun - timedelta(weeks=RANGE)

    # Запас на праздники и UTC
    dt_0 = dt_1 - timedelta(days=10)

    positions = Position.objects.filter(account_id=account_id)
    positions = positions.order_by("contract__sec_type", "contract__sid")
    positions = positions.prefetch_related()

    for position in positions:
        # Позиция нулевая и давно не обновлялась
        if not bool(position.amount) and position.updated_at < dt_0:
            continue
        if position.avg_price:
            if position.contract.sec_type in [Contract.Type.cash, Contract.Type.crypto]:
                price = f"{position.avg_price:0.4f}"
            else:
                price = f"{position.avg_price:0.2f}"
        else:
            price = "--"
        sid = position.contract.sid
        name = (sid.split("_", 1)[1]).replace("_", " ")
        res.append(
            {
                "symbol": sid,  # TODO: remove
                "sid": sid,
                "sec_type": position.contract.sec_type,
                "name": name,  # TODO: remove
                "amount": position.amount,
                "avg_price": price,
                "unrealized_pnl": position.unrealized_pnl,
                "updated": position.updated_at,
            }
        )

    return res


def account_status(pk):
    return Account.objects.get(pk=pk)


async def pnl_report(rc, pk):
    pr = await sync_to_async(PerformanceReport, thread_sensitive=False)(
        redis_client=rc, account_id=pk
    )
    report = await sync_to_async(pr.generate, thread_sensitive=False)()
    res = {
        "account_id": pk,
        "assets": list(report.values()),
    }
    return res


def account_orders(pk):
    return get_orders(pk, limit=50)


def account_positions(pk):
    pos = get_positions(account_id=pk)

    # FOR TEST
    pos = list(pos)
    for el in pos:
        if el["unrealized_pnl"]:
            rnd = round(el["unrealized_pnl"] * Decimal(random.uniform(-0.1, 0.1)), 2)
            el["unrealized_pnl"] = rnd

    res = {
        "account_id": pk,
        "assets": pos,
    }
    return res


class ChatConsumer(AsyncWebsocketConsumer):
    max_delay_sec = 30

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.chat_id = random.randint(1000, 9999)
        self.closed = False
        self.account_id = None

        self.rc = redis.Redis(
            host=settings.TRADIS_HOST,
            port=settings.TRADIS_PORT,
            db=settings.TRADIS_DB,
            decode_responses=True,
        )

        # Время сообщение от клиента
        self.last_incoming = time.monotonic() - 1000

        # Время последней отправки разных штук
        self.last_status = time.monotonic() - 1000
        self.last_pnl = time.monotonic() - 1000

    async def connect(self):
        await self.accept()
        self.last_incoming = time.monotonic()
        asyncio.create_task(self.periodic_status())
        # asyncio.create_task(self.periodic_status_long())

    async def disconnect(self, close_code):
        print(f"{self.chat_id} was DISCONNECTED with code:", close_code)
        self.closed = True

    async def receive(self, text_data):
        self.last_incoming = time.monotonic()

        print(f"incoming MESSAGE [{self.chat_id}]: {text_data}")

        msg = json.loads(text_data)

        if msg["type"] == "command":
            if msg["name"] == "change_account":
                self.account_id = msg["params"]["account_id"]
                self.last_status = 0
                self.last_pnl = 0

    async def send_status(self):
        self.last_status = time.monotonic()
        account = await sync_to_async(account_status, thread_sensitive=False)(
            pk=self.account_id
        )

        utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
        update_delay = round((utc_now - account.updated_at).total_seconds(), 2)

        payload = {
            "type": "message",
            "data_type": "account",
            "data": {
                "net_value": str(account.net_value),
                "margin_used": str(account.margin_used),
                "daily_pnl": str(account.daily_pnl),
                "unrealized_pnl": str(account.unrealized_pnl),
                "paper": account.paper,
                "account_id": account.pk,
                "account_uid": str(account.uid),
                "random": "%.2f" % (random.randint(100_00, 1000_00) / 100),
                "update_delay": f"{update_delay}",
            },
        }
        await self.send(text_data=json.dumps(payload))

    async def send_orders(self):
        orders = await sync_to_async(account_orders, thread_sensitive=False)(
            pk=self.account_id
        )
        payload = {
            "type": "message",
            "data_type": "orders",
            "data": orders,
        }
        await self.send(text_data=json.dumps(payload, default=str))

    async def send_positions(self):
        positions = await sync_to_async(account_positions, thread_sensitive=False)(
            pk=self.account_id
        )
        payload = {
            "type": "message",
            "data_type": "positions",
            "data": positions,
        }
        await self.send(text_data=json.dumps(payload, default=str))

    async def send_pnl_report(self):
        self.last_pnl = time.monotonic()
        # pnl = await sync_to_async(pnl_report, thread_sensitive=False)(rc=self.rc, pk=self.account_id)
        pnl = await pnl_report(rc=self.rc, pk=self.account_id)
        payload = {
            "type": "message",
            "data_type": "pnl",
            "data": pnl,
        }
        await self.send(text_data=json.dumps(payload, default=str))

    async def periodic_status(self):
        """
        Таск, отправляющий healthcheck-сообщения через равные интервалы.
        Остановить и закрыть сокет, если он был закрыт клиентом или отвалился.
        """
        while True:
            if not self.account_id:
                await asyncio.sleep(0.1)
                continue

            if time.monotonic() - self.last_incoming > self.max_delay_sec:
                print("PING DELAY, close connection", self.chat_id)
                await self.close(1000)
                return

            if self.closed:
                print("connection was CLOSED", self.chat_id)
                await self.close(1001)
                return

            if time.monotonic() - self.last_status > 1:
                self.last_status = time.monotonic()
                await self.send_status()
                await self.send_positions()
                await self.send_orders()

            if time.monotonic() - self.last_pnl > 15:
                await self.send_pnl_report()

            await asyncio.sleep(0.1)
