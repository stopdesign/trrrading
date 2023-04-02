import json
import logging
from decimal import Decimal

import redis

from main.models import Account as DBAccount
from main.models import Order as DBOrder
from main.models import Position as DBPosition
from trader.data_types import Order, Position

log = logging.getLogger("sync_client")


class SyncClient:
    """
    Клиент сервиса, синхронизирующего базу с брокером.
    Пока работает через базу данных на чтение и через pubsub на запись.
    """

    def __init__(self, positions, orders, account):
        self.account = account
        self.positions = positions
        self.orders = orders

        self.db_account = DBAccount.objects.get(uid=self.account["uid"])
        self.update_broker_data({"types": ["init"]})

        self.redis_client = redis.Redis()

    def place_order(self, order: Order):
        action = {
            "action": "create",
            "local_id": order.local_id,
            "sid": order.sid,
            "amount": order.amount,
            "type": order.type,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
        }
        self.redis_client.publish("BOT_ACTIONS", json.dumps(action, default=str))

        # как-то нужно добавить ордер в ордеры, но так, чтобы он автоматически
        # удалился при появлении его в TWS
        self.orders.append(order)  # Нужно ли добавлять ордер сюда ???

    def update_order(self, order: Order, **kwargs):
        action = {
            "action": "update",
            "local_id": order.local_id,
            "amount": order.amount,
            "stop_price": kwargs.get("stop_price"),
        }
        self.redis_client.publish("BOT_ACTIONS", json.dumps(action, default=str))

    def cancel_order(self, order: Order):
        action = {
            "action": "cancel",
            "local_id": order.local_id,
        }
        self.redis_client.publish("BOT_ACTIONS", json.dumps(action, default=str))

    def update_broker_data(self, payload):
        # TODO: Смотреть payload и обновлять только нужный тип объектов

        # обновить данные в self.positions, self.account...
        db_positions = DBPosition.objects.filter(account=self.db_account)
        db_positions = db_positions.order_by("-id")[:100]

        for key in list(self.positions.keys()):
            self.positions.pop(key)
        for position in db_positions:
            sid = position.contract.sid
            self.positions[sid] = Position(
                sid=sid,
                capital=Decimal(100_000),
                amount=position.amount,
                avg_price=position.avg_price,
            )

        self.orders.clear()
        # вытащить только актуальные ордеры, а не всю историю
        db_orders = DBOrder.objects.filter(account=self.db_account)
        db_orders = db_orders.order_by("-id")[:10]

        for order in db_orders:
            amount = order.amount
            if order.action == DBOrder.Side.sell:
                amount = -order.amount
            o = Order(
                sid=order.contract.sid,
                local_id=order.local_id,
                type=order.type,
                amount=amount,
                status=order.status,
                fill_price=order.avg_fill_price,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                created_at=order.created_at,
            )
            self.orders.append(o)
