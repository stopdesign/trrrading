import logging
from decimal import Decimal
from time import monotonic, sleep

import simplejson as json
from django.db.models import Q
from termcolor import colored

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

    ########################################
    # Отправка команд в Sync

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

    ########################################
    # Актуализация состояния объектов

    def update_broker_data(self, payload):
        # TODO: Смотреть payload и обновлять только нужный тип объектов

        dt = monotonic()
        self.sync_positions()
        self.sync_orders()
        txt = f"update_broker_data done in {(monotonic() - dt):0.3f} sec, "
        txt += f"{len(self.positions)} positions, {len(self.orders)} orders"
        log.info(colored(txt, "green"))

    def sync_positions(self):
        """
        В self.positions должны быть все позиции из базы плюс нулевые
        позиции для инструментов, которые есть в стратегиях, но не в базе.

        Не хотелось бы каждый раз создавать новый list.

        Данные будут использованы в другом потоке (иногда в тот же момент).
        """

        db_positions = DbPosition.objects.filter(account=self.db_account)
        db_positions = db_positions.select_related("contract")
        db_positions_by_sid = {p.contract.sid: p for p in db_positions}

        # Все ключи, которые должны быть в self.positions
        sids = set(list(self.positions.keys()) + list(db_positions_by_sid.keys()))

        for sid in sids:
            if db_position := db_positions_by_sid.get(sid):
                amount = Decimal(db_position.amount)
                price = db_position.avg_price or Decimal("nan")
            else:
                amount = Decimal(0.0)
                price = Decimal("nan")
            self.positions[sid] = Position(sid, amount=amount, avg_price=price)

    def sync_orders(self):
        """
        Актуализация состояния ордеров. Обновить всё старое и добавить новое.

        Ордеры с local_id должны остаться в массиве, у них обновляются поля.

        Ордеры без local_id не попадают в выборку.
        Они были созданы кем-то другим, пусть сами и разбираются.

        Можно ограничить выборку только теми sid, которые нужны боту.

        Все активные ордеры должны попасть в массив, даже если они старые.
        """
        sids = list(self.positions.keys())
        local_ids = {o.local_id for o in self.orders if o.local_id}

        done = ["Cancelled", "Filled"]

        db_orders = DbOrder.objects.select_related("contract")
        db_orders = db_orders.filter(account=self.db_account, contract__sid__in=sids)

        # Выбрать ордеры с известными local_id или активным статусом
        db_orders = db_orders.filter(Q(local_id__in=local_ids) | ~Q(status__in=done))

        # Исключить ордеры без local_id
        db_orders = db_orders.exclude(Q(local_id__isnull=True) | Q(local_id=""))

        db_orders_by_local_id = {o.local_id: o for o in db_orders}

        for order in self.orders:
            db_order = db_orders_by_local_id.get(order.local_id)

            if not db_order:
                log.error(f"Order {order} not found in the DB")
                order.status = "Gone"
                continue

            amount = db_order.amount
            if db_order.action == DbOrder.Side.sell:
                amount = -db_order.amount

            order = Order(
                sid=db_order.contract.sid,
                local_id=db_order.local_id,
                type=db_order.type,
                amount=amount,
                status=db_order.status,
                fill_price=db_order.avg_fill_price,
                limit_price=db_order.limit_price,
                stop_price=db_order.stop_price,
                created_at=db_order.created_at,
            )
