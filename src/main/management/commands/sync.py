import json
import logging
from posixpath import abspath
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis
import yaml
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from ibapi.order import Order as IBOrder
from termcolor import colored, cprint

from ibkr_api.client import IbContract, IBThread
from ibkr_api.ib_sync import IBSync
from main.models import Account, Contract, Order, Position, Trade

# Логгер для этого файла
log = logging.getLogger("sync")


DEF_CONFIG = "../config/bot.yaml"

BOT_ID_PREFIX = "bot_"

SYNC_CHANNEL = "SYNC"

DT_FMT = "%Y-%m-%d %H:%M:%S"


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


"""
Важные ошибки, которые нужно обработать:
ERROR 1100 Connectivity between IB and Trader Workstation has been lost.
ERROR 1102 Connectivity between IB and Trader Workstation has been restored...
"""


class IBSyncExtended(IBSync):
    def __init__(self, redis_client):
        super().__init__()
        self.redis_client = redis_client
        self.lock_for_sync = False  # запрет обработки событий до синхронизации базы

    def pnl(
        self, reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float
    ):
        if self.lock_for_sync:
            return

        account = Account.objects.get(uid=self.account_id)

        values = self.values[account.uid]

        account.daily_pnl = dailyPnL
        account.unrealized_pnl = unrealizedPnL
        account.realized_pnl = realizedPnL

        # TODO: добавить Cushion — Excess liquidity as a percentage of net liquidation value

        # FIXME: KeyError: 'NetLiquidation'; pnl может приходить раньше values.

        account.net_value = values["NetLiquidation"]
        account.margin_used = values["MaintMarginReq"]
        account.cash_value = values["CashBalance"]
        account.ex_liq_sec = values["ExcessLiquidity-S"]
        account.ex_liq_com = values["ExcessLiquidity-C"]

        account.save()

    def updatePortfolio(
        self,
        contract,
        position,
        marketPrice,
        marketValue,
        averageCost,
        unrealizedPNL,
        realizedPNL,
        accountName,
    ):
        if self.lock_for_sync:
            return

        account = Account.objects.get(uid=accountName)

        sid = self.sid_for_contract(contract)

        db_position = Position.objects.get(account=account, contract__sid=sid)

        if db_position.amount != position:
            log.error(f"Position missmatch: db = {db_position.amount}, ib = {position}")

        db_position.avg_price = averageCost
        db_position.unrealized_pnl = unrealizedPNL
        db_position.save(update_fields=["avg_price", "unrealized_pnl"])

        # TODO:
        # 1. Проверить, что были изменения в полях
        # 2. ???
        # Боту не нужно знать pnl, такие обновления приходят слишком часто.

        # TODO: взять из позиции sid и поставить вместо contract

        action = {
            "types": ["position"],
            "info": {"contract": sid, "amount": db_position.amount},
        }
        msg = json.dumps(action, default=str)
        a = self.redis_client.publish(SYNC_CHANNEL, msg)
        log.info(f"To Redis: {msg}, {a}")

    def orderStatus(
        self,
        orderId,
        status: str,
        filled: Decimal,
        remaining: Decimal,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        """
        Что за хрень здесь происходит?

        Событие orderStatus приходит, когда меняется статус ордера,
        и после любых изменений ордера. Но событие не содержит сам ордер,
        поэтому ордер добывается из сохраненных событий openOrder.

        В openOrder приходят данные ордера и контракта, но нет
        оставшегося количества. Если мы отслеживаем исполнение,
        то нет смысла там сохранять ордер.
        """
        if self.lock_for_sync:
            return

        av_fill_price = avgFillPrice if avgFillPrice < 10**10 else None

        if permId and permId in self._orders_by_pid:
            # TODO: для активного ордера проверить время его получения
            order, contract, state = self._orders_by_pid[permId]
        else:
            log.error(f"Order not found, {permId}")
            return

        log.info(
            colored(
                (
                    f"OrderStatus: oId: {orderId}, "
                    f"pId: {permId}, {state.status} >> {status}, "
                    f"amnt: {filled}/{remaining}, "
                    f"price: {order.lmtPrice}, "
                    f"fill_pr: {av_fill_price}, "
                    f"whyHeld: {whyHeld}"
                ),
                "blue",
            )
        )

        # Обновление статуса ордера в кэше
        state.status = status
        self._orders_by_pid[permId] = order, contract, state

        sid = self.sid_for_contract(contract)

        # TODO: закешировать?
        account = Account.objects.get(uid=order.account)

        with transaction.atomic():
            # Контракт достается из базы или создается
            try:
                db_contract = Contract.objects.get(sid=sid)
            except Contract.DoesNotExist:
                log.warn(f"Create new contract {sid}")
                cd = self.get_contract_details(contract)
                db_contract = Contract.from_ib(contract, cd, sid)
                db_contract.save()

            try:
                # Два варианта:
                # - ордер создан на стороне IB, мы сразу знаем permId
                # - ордер создан через базу и лежит там без permId
                # Про ref нужно понимать, что чужие ref могут быть не уникальными.
                # Если в ref лежит наш идентификатор, то нужно сначала искать ордер
                # в базе по нему. Если не нашлось, то поискать по permId.

                log.info(f"IBOrder: perm_id: {order.permId}, ref: {order.orderRef}")

                db_order = None

                if BOT_ID_PREFIX and BOT_ID_PREFIX in str(order.orderRef):
                    try:
                        db_order = Order.objects.get(local_id=order.orderRef)
                        db_order.order_id = order.permId  # сохранить себе permId
                    except Order.DoesNotExist:
                        log.warn(f"Bot order not found in DB: {order.orderRef}")

                # Ордер не из бота или не нашелся
                if not db_order:
                    db_order = Order.objects.get(order_id=order.permId)

                db_order.amount = order.totalQuantity
                db_order.limit_price = order.lmtPrice
                db_order.stop_price = order.auxPrice

            except Order.DoesNotExist:
                # Если ордера всё еще нет в базе - создать
                db_order = Order.from_ib(order, account, db_contract, state)

            log.info(f"Order in DB {db_order}")

            # Используется последнее известное значение позиции контракта
            try:
                known_ib_position, avg_price = self._positions_by_conid[contract.conId]
            except KeyError:
                known_ib_position, avg_price = 0, None

            # Редактирование или создание позиции
            try:
                # TODO: не редактировать, если не было изменений
                # orderStatus возникает при редактировании цены ордера,
                # поэтому часто это не связано с изменением позиции.
                db_position = Position.objects.get(
                    account=account, contract=db_contract
                )
                if db_position.amount != known_ib_position:
                    log.info(f"Pos, DB: {db_position.amount}, IB: {known_ib_position}")
                    db_position.amount = known_ib_position
                    db_position.avg_price = avg_price
                    db_position.save()
            except Position.DoesNotExist:
                log.info(colored(f"Pos, DB: --, IB: {known_ib_position}", "green"))
                db_position = Position.from_ib(
                    account, db_contract, known_ib_position, avg_price
                )
                db_position.save()

            db_order.avg_fill_price = av_fill_price
            db_order.filled = filled
            db_order.status = status
            db_order.save()

            action = {"types": ["order", "position"]}
            msg = json.dumps(action, default=str)
            a = self.redis_client.publish(SYNC_CHANNEL, msg)
            log.info(f"To Redis: {msg}, {a}")

    #################################

    def process_bot_action(self, message):
        data = json.loads(message.get("data").decode())
        log.info(colored(f"From Redis: {data}", "white"))

        if data.get("action") == "create":
            self.create_order(data)
            return

        if data.get("action") == "update":
            self.update_order(data)
            return

        if data.get("action") == "cancel":
            self.cancel_order(data)
            return

        log.error(f"Unknown bot action: {message}")

    def create_order(self, data):
        """
        Создание ордера в IB
        """
        # ib_contract - нужен для отправки ордера в IB
        # db_contract - нужен для сохранения ордера в базе

        sid = data["sid"]

        ib_contract = self.contract_for_sid(sid)

        db_account = Account.objects.get(uid=self.account_id)
        db_contract = Contract.objects.get(sid=sid)

        oid = self.nextValidOrderId
        self.nextValidOrderId += 1

        stop_price = float(data.get("stop_price"))

        amount = Decimal(data.get("amount"))
        action = "BUY" if amount > 0 else "SELL"
        side = Order.Side.buy if amount > 0 else Order.Side.sell

        local_id = data.get("local_id")

        # Отправить ордер в TWS
        ib_order = IBOrder()
        ib_order.orderId = oid
        ib_order.orderRef = local_id
        ib_order.action = action
        ib_order.totalQuantity = abs(amount)

        # order.goodTillDate = "20200923 15:13:20 EST"
        # order.tif = "GTD"

        # FIXME: поддерживать разные типы ордеров

        # ib_order.orderType = "MKT"
        # order = Order.market_order(db_account, db_contract, side, abs(amount))

        ib_order.orderType = "STP LMT"
        ib_order.outsideRth = True
        ib_order.auxPrice = stop_price
        if ib_order.action == "BUY":
            ib_order.lmtPrice = stop_price + 0.25
        else:
            ib_order.lmtPrice = stop_price - 0.25

        db_order = Order.stop_order(db_account, db_contract, side, abs(amount))

        log.info(colored(f"Create, ib_order: {ib_order}", "green"))

        # создать ордер в базе данных
        db_order.local_id = local_id
        db_order.save()

        self.placeOrder(oid, ib_contract, ib_order)

        db_order.status = "Sent"
        db_order.save(update_fields=["status"])

    def update_order(self, data):
        """
        Редактирование ордера в IB
        """
        local_id = data.get("local_id")
        stop_price = Decimal(data.get("stop_price"))

        for ib_order, contract, orderState in self._orders_by_pid.values():
            if ib_order.orderRef == local_id:
                log.info(colored(f"Update, ib_order: {ib_order}", "yellow"))
                ib_order.auxPrice = stop_price
                if ib_order.action == "BUY":
                    ib_order.lmtPrice = stop_price + Decimal(0.25)
                else:
                    ib_order.lmtPrice = stop_price - Decimal(0.25)
                self.placeOrder(ib_order.orderId, contract, ib_order)

                return

        log.error(f"Order not found: {data}")

    def cancel_order(self, data):
        """
        Отмена ордера в IB
        """
        local_id = data.get("local_id")

        inactive = ["Filled", "Cancelled", "ApiCancelled", "Inactive"]

        # FIXME: _orders_by_pid обновляется в openOrder и не ловит состояние canceled
        for ib_order, contract, orderState in self._orders_by_pid.values():
            if ib_order.orderRef == local_id and orderState.status not in inactive:
                log.info(colored(f"Cancel, ib_order: {ib_order}", "magenta"))
                self.cancelOrder(ib_order.orderId, "")
                return

        log.error(f"Order not found: {data}")


##################
# инициализация и синхронизация
# TODO: разбить initial_sync на кусочки поменьше


def get_executions(ib):
    account = Account.objects.get(uid=ib.account_id)

    # TODO: выбрать только последние пару дней
    trades = Trade.objects.filter(account=account)
    trades_by_exec_id = {t.exec_id: t for t in trades}

    orders = Order.objects.filter(account=account)
    orders_by_id = {o.order_id: o for o in orders}

    executions = ib.get_executions()

    trades_to_create = []
    updated_orders = []

    for _, exec in executions:
        if exec.execId not in trades_by_exec_id:
            if order := orders_by_id.get(exec.permId):
                log.info(colored("New trade: " + f"{exec}"[-120:], "cyan"))
                trades_to_create.append(Trade.from_ib(exec, account, order))
                updated_orders.append(order)
            else:
                log.error(f"Execution without order: {exec.execId}, o: {exec.permId}")

    if trades_to_create:
        Trade.objects.bulk_create(trades_to_create)

        action = {"types": ["trade"]}
        a = ib.redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"To Redis: {action}, {a}")

    # Бывает так, что событие ордера не было поймано вовремя.
    # Тогда среднюю цену можно восстановить только по сделкам.

    # Пересчитать цены ордеров, для которых загружены сделки.
    # updated_orders
    # Получить сделки для этих ордеров, посчитать, сохранить.
    # trades = Trade.objects.filter(account=account)


def initial_sync(ib: IBSyncExtended):
    """
    Начальную синхронизацию лучше не объединять с обновлением,
    т.к. для завершенных ордеров не приходит статус. Это меняет алгоритм.

    Проще сделать всю синхронизацию отдельно, в одной транзакции.

    - открыть транзакцию
    - запросить всё
    - сохранить всё
    - запросить всё еще раз
    - если ничего не поменялось, применить транзакцию
    - если поменялось - начать заново
    """

    # Получить данные из базы

    log.info(colored(f"Start initial_sync, account: {ib.account_id}", attrs=["bold"]))

    account = Account.objects.get(uid=ib.account_id)

    positions = Position.objects.filter(account=account)
    positions_by_sid = {p.contract.sid: p for p in positions}

    orders = Order.objects.filter(account=account)
    orders_by_id = {o.order_id: o for o in orders}

    contracts = Contract.objects.all()
    contracts_by_sid = {c.sid: c for c in contracts}

    # Получить данные из IB

    ib_orders = ib.get_orders()
    ib_positions = ib.get_positions()
    ib_executions = ib.get_executions()

    ############
    # Создаются контракты, которых не было в базе

    contracts_to_create = []
    all_contracts = [r[0] for r in ib_orders] + [r[1] for r in ib_positions]
    uniq_contracts = {c.conId: c for c in all_contracts}

    for con_id, contract in uniq_contracts.items():
        cd = None
        if not contract.primaryExchange:
            cd = ib.get_contract_details(contract)[0]
            contract = cd.contract
            uniq_contracts[con_id] = contract
        sid = ib.sid_for_contract(contract)
        if sid not in contracts_by_sid:
            if not cd:
                cd = ib.get_contract_details(contract)[0]
            c = Contract.from_ib(contract, cd, sid)
            contracts_by_sid[sid] = c
            contracts_to_create.append(c)
            log.info(f"Create contract: {c.sid}")

    Contract.objects.bulk_create(contracts_to_create)

    ############
    # Ордеры

    orders_to_create = []

    for contract, order, state in ib_orders:
        # log.info(f"IB ORDER {order} > {order.orderRef}, {state.status}")

        if not order.permId:
            continue

        if db_order := orders_by_id.get(order.permId):
            # TODO: проверить изменения ордеров из базы, которые не финализированы
            # FIXME: сделать нормально
            if state.status != db_order.status:
                msg = f"UPDATE in DB {order} {orders_by_id[order.permId]}"
                log.info(colored(msg, "magenta"))
                db_order.status = state.status
                db_order.save(update_fields=["status"])
        else:
            # contract
            sid = ib.sid_for_contract(contract)
            db_c = contracts_by_sid[sid]
            orders_to_create.append(Order.from_ib(order, account, db_c, state))

    if orders_to_create:
        Order.objects.bulk_create(orders_to_create)

        action = {"types": ["order"]}
        a = ib.redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"To Redis: {action}, {a}")

    ############
    # Позиции

    positions_to_create = []

    # Всем обнуляю значения, но пока не сохраняю
    for position in positions_by_sid.values():
        position.amount = 0
        position.avg_price = None
        # position.unrealized_pnl = None

    for acnt, con, pos, avgCost in ib_positions:
        contract = uniq_contracts[con.conId]
        sid = ib.sid_for_contract(contract)

        db_c = contracts_by_sid[sid]

        if acnt != account.uid:
            log.warn(f"Skip wrong account: {acnt}")
            continue

        avg_price = avgCost / int(db_c.multiplier)  # * 100  # ???

        if sid in positions_by_sid:
            # update position
            position = positions_by_sid[sid]
            position.avg_price = avg_price
            position.amount = pos
        else:
            # create position
            position = Position.from_ib(account, db_c, pos, avg_price)
            positions_to_create.append(position)

    positions_to_update = positions_by_sid.values()

    if positions_to_create or positions_to_update:
        Position.objects.bulk_create(positions_to_create)
        Position.objects.bulk_update(positions_to_update, ["avg_price", "amount"])

        action = {"types": ["position"]}
        a = ib.redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"To Redis: {action}, {a}")

    log.info("Check initial_sync integrity")

    ib_orders_2 = ib.get_orders()
    ib_positions_2 = ib.get_positions()
    ib_executions_2 = ib.get_executions()

    # Сравнить данные ib_* и ib_*_2.
    # Если одинаковые, то всё ok.
    if len(ib_orders) != len(ib_orders_2):
        raise Exception("Orders updated")

    if len(ib_positions) != len(ib_positions_2):
        raise Exception("Positions updated")

    if len(ib_executions) != len(ib_executions_2):
        raise Exception("Executions updated")


############################


class Command(BaseCommand):
    """
    Синхронизация состояния базы с IB через TWS.
    """

    def add_arguments(self, parser):
        parser.add_argument("--config", type=str, dest="config", default=DEF_CONFIG)

    def handle(self, **kwargs):
        config = yaml.full_load(open(abspath("../config/bot.yaml")))
        gateway = config["gateway"]

        # TODO: настроить из конфига
        redis_client = redis.Redis()
        pubsub = redis_client.pubsub()

        ib = IBSyncExtended(redis_client)
        ib.lock_for_sync = True

        # NOTE: не уверен, что правильно подписываться
        # снаружи, но "event loop" находится здесь.
        pubsub.subscribe("BOT_ACTIONS")

        last_conn_check = datetime.min
        last_exec_check = datetime.min

        try:
            while True:
                now = datetime.utcnow()
                go_conn_check = now - last_conn_check > timedelta(seconds=11)
                go_exec_check = now - last_exec_check > timedelta(seconds=13)

                # Обработка команд от бота
                if ib and ib.isConnected():
                    try:
                        message = pubsub.get_message(timeout=0.1)
                        if message and message.get("type") == "message":
                            ib.process_bot_action(message)
                    except Exception as e:
                        log.error(f"Redis pubsub get_message error: {e}")
                        log.exception(e)
                        pass

                # регулярные запросы
                if go_exec_check and ib and ib.isConnected():
                    last_exec_check = datetime.utcnow()
                    try:
                        get_executions(ib)
                    except Exception as e:
                        log.error(f"Get executions error: {e}")

                # Переконнект
                if go_conn_check and not ib.isConnected():
                    last_conn_check = datetime.utcnow()

                    # NOTE: плохо, что приходится пересоздавать объект
                    ib = IBSyncExtended(redis_client)
                    ib.lock_for_sync = True

                    ib.connect(gateway["host"], gateway["port"], 0)

                    # Endless message loop
                    IBThread(ib).start()

                    # Не соединилось, попробовать еще раз
                    if not ib.isConnected():
                        continue

                    # Check if the API is connected via orderid
                    while True:
                        if ib.nextValidOrderId > 0:
                            cprint(f"Connected", "green")
                            break
                        time.sleep(0.5)

                    # Синхронизация базы с IB
                    while True:
                        ib.lock_for_sync = True
                        try:
                            with transaction.atomic():
                                initial_sync(ib)
                                break
                        except Exception as e:
                            log.error(f"Initial sync error: {e}")
                            log.exception(e)
                            time.sleep(3)
                        finally:
                            ib.lock_for_sync = False

                    # Начать real-time обработку сообщений
                    # ib.real_time = True

                    # Нет ничего про профит, поэтому все равно придется брать AccountUpdates
                    # ib.reqAccountSummary(ib.r_id, "All", "NetLiquidation,InitMarginReq")
                    # time.sleep(0.1)

                    # С этой хренью новые ордеры из TWS получают id от данного клиента.
                    # Работает только для подключения с ClientId = 0.
                    # Пока непонятно, что с ордерами из мобильного приложения, например.
                    ib.reqAutoOpenOrders(True)
                    time.sleep(0.1)

                    # это подписка, но её нельзя отменить
                    ib.reqAccountUpdates(True, ib.account_id)
                    time.sleep(0.1)

                    # На это нельзя подписываться много раз, заебет.
                    # Но при одной подписке оно реально приходит на каждое изменение.
                    # Выглядит удобно.
                    ib.reqPnL(ib.r_id, ib.account_id, "")
                    time.sleep(0.1)

                    # Получить исторические сделки, посчитать av_fill_price
                    try:
                        get_executions(ib)
                    except Exception as e:
                        log.error(f"Get executions error: {e}")

                time.sleep(0.5)

        except (KeyboardInterrupt, SystemExit):
            print()
            log.info("Stop\n")

        finally:
            if ib:
                ib.disconnect()
