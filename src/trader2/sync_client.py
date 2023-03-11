import json
import logging
from decimal import Decimal

import redis

from data_types import Order, Position
from main.models import Account as DBAccount
from main.models import Order as DBOrder
from main.models import Position as DBPosition

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
        self.update_broker_data()

    def place_order(self, order):
        redis_client = redis.Redis()
        action = {"amount": order.amount, "local_id": order.local_id}
        redis_client.publish("BOT_ACTIONS", json.dumps(action, default=str))

        # как-то нужно добавить ордер в ордеры, но так, чтобы он автоматически
        # удалился при появлении его в TWS
        self.orders.append(order)  # Нужно ли добавлять ордер сюда ???

    def update_broker_data(self):
        # обновить данные в self.positions, self.account...
        db_positions = DBPosition.objects.filter(account=self.db_account)

        res = {}
        for position in db_positions:
            ticker = position.contract.ticker
            res[ticker] = Position(
                symbol=ticker,
                capital=Decimal(100_000),
                amount=position.amount,
                avg_price=position.avg_price,
            )
        self.positions = res

        res = []
        # вытащить только актуальные ордеры, а не всю историю
        db_orders = DBOrder.objects.filter(account=self.db_account)
        for order in db_orders:
            o = Order(
                instrument=order.contract.ticker,
                local_id=order.local_id,
                type=order.type,
                amount=order.amount,
                status=order.status,
                fill_price=order.avg_fill_price,
                limit_price=order.limit_price,
            )
            res.append(o)
        self.orders = res
