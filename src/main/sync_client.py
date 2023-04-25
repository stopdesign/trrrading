import logging
from decimal import Decimal
from time import sleep

import simplejson as json

from main.models import Account as DbAccount
from main.models import Order as DbOrder
from main.models import Position as DbPosition
from trader.data_types import Order, Position

log = logging.getLogger("sync_client")


BOT_CHANNEL = "BOT_ACTIONS"
SYNC_CHANNEL = "SYNC"


class SyncClient:
    """
    Клиент сервиса, синхронизирующего базу с брокером.
    Пока работает через базу данных на чтение и через pubsub на запись.
    """

    def __init__(self, positions, orders, account, redis_client):
        self.account = account
        self.positions = positions
        self.orders = orders
        self.redis_client = redis_client

        # Разделение live и paper по разным каналам pubsub
        redis_db = redis_client.connection_pool.connection_kwargs["db"]
        self.bot_channel = f"{redis_db}_{BOT_CHANNEL}"
        self.sync_channel = f"{redis_db}_{SYNC_CHANNEL}"

        log.info(f"bot_channel: {self.bot_channel}")
        log.info(f"sync_channel: {self.sync_channel}")

        self.db_account = DbAccount.objects.get(uid=self.account["uid"])
        self.update_broker_data({"types": ["init"]})

    def place_order(self, order: Order):
        action = {"action": "create_order", "order": order.as_dict()}
        msg = json.dumps(action, default=str, ignore_nan=True)
        self.redis_client.publish(self.bot_channel, msg)

        # как-то нужно добавить ордер в ордеры, но так, чтобы он автоматически
        # удалился при появлении его в TWS
        self.orders.append(order)  # NOTE: Нужно ли добавлять ордер сюда ???

    def update_order(self, order: Order, **kwargs):
        order_dict = order.as_dict()
        for k, v in kwargs.items():
            order_dict[k] = v
        action = {"action": "update_order", "order": order_dict}
        msg = json.dumps(action, default=str, ignore_nan=True)
        self.redis_client.publish(self.bot_channel, msg)

        # NOTE: Нужно ли обновлять значение stop_price в self.orders ???

    def cancel_order(self, order: Order):
        action = {"action": "cancel_order", "order": order.as_dict()}
        msg = json.dumps(action, default=str, ignore_nan=True)
        self.redis_client.publish(self.bot_channel, msg)

    def listen(self):
        """
        Подписка на события в Redis pubsub.
        """
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(self.sync_channel)

        while True:
            try:
                message = pubsub.get_message(timeout=100)
            except Exception as e:
                log.error(f"Redis pubsub get_message error: {e}")
                sleep(1)
                continue

            try:
                if message and message.get("type") == "message":
                    log.info(f"NEW broker_event: {message.get('data')}")
                    self.update_broker_data(message.get("data"))
            except Exception as e:
                log.exception(e)

    def update_broker_data(self, payload):
        # TODO: Смотреть payload и обновлять только нужный тип объектов
        # init обновляет всё

        # обновить данные в self.positions, self.account...
        db_positions = DbPosition.objects.filter(account=self.db_account)
        db_positions = db_positions.order_by("-updated_at")[:100]

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

        # FIXME: обращения к self.orders и self.positions из разных потоков
        self.orders.clear()

        # FIXME: вытащить актуальные ордеры, а не хрен знает что
        db_orders = DbOrder.objects.filter(account=self.db_account)
        db_orders = db_orders.order_by("-updated_at")[:100]

        for order in db_orders:
            amount = order.amount
            if order.action == DbOrder.Side.sell:
                amount = -order.amount
            # log.error(f"db order: {order}, local_id: {order.local_id}")
            o = Order(
                sid=order.contract.sid,
                # FIXME: хуйня какая-то (чтобы конструктор не создал local_id)
                local_id=order.local_id or "",
                type=order.type,
                amount=amount,
                status=order.status,
                fill_price=order.avg_fill_price,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
                created_at=order.created_at,
            )
            self.orders.append(o)
