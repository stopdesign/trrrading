import json
import logging
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

from ibkr_api.client import IBThread, IbContract
from ibkr_api.ib_sync import IBSync
from main.models import Account, Contract, Order, Position, Trade

# Логгер для этого файла
log = logging.getLogger("sync")


DEF_CONFIG = "../config/bot.yaml"

APP = None

BOT_ID_PREFIX = "bot_"

DT_FMT = "%Y-%m-%d %H:%M:%S"


def ts_to_dt(ts):
    return datetime.utcfromtimestamp(ts)


redis_client = redis.Redis()
pubsub = redis_client.pubsub()


SYNC_CHANNEL = "SYNC"

"""
Важные ошибки, которые нужно обработать:
ERROR 1100 Connectivity between IB and Trader Workstation has been lost.
ERROR 1102 Connectivity between IB and Trader Workstation has been restored...
"""


def pnl(reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float):
    account = Account.objects.get(uid=APP.account_id)
    values = APP.values[account.uid]

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

    # Этих слишком много. Депозит постоянно обновляется.
    # action = {"types": ["account"]}
    # a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
    # log.info(f"Redis sync-message: {action}, {a}")


def updatePortfolio(
    contract,
    position,
    marketPrice,
    marketValue,
    averageCost,
    unrealizedPNL,
    realizedPNL,
    accountName,
):
    account = Account.objects.get(uid=accountName)
    db_position = Position.objects.get(account=account, contract__conid=contract.conId)

    if db_position.amount != position:
        log.error(f"Position missmatch: db = {db_position.amount}, ib = {position}")

    db_position.avg_price = averageCost
    db_position.unrealized_pnl = unrealizedPNL
    db_position.save(update_fields=["avg_price", "unrealized_pnl"])

    action = {
        "types": ["position"],
        "info": {"contract": contract.conId, "amount": db_position.amount},
    }
    a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
    log.info(f"Redis sync-message: {action}, {a}")


def process_bot_action(ib, message):
    data = json.loads(message.get("data").decode())
    log.info(colored(f"message.data: {data}", "yellow"))

    if data.get("action") == "create":
        create_order(ib, data)
        return

    if data.get("action") == "update":
        update_order(ib, data)
        return

    if data.get("action") == "cancel":
        cancel_order(ib, data)
        return

    log.error(f"Unknown bot action: {message}")


def create_order(ib, data):

    # TODO: сделать контракт из data.sid

    # ib_contract - нужен для отправки ордера в IB - может ли быть без conid?
    # db_contract - нужен для сохранения ордера в базе

    contract = IbContract("")
    contract = FutContract("MES", "MESM3", exchange="CME")

    print("contract.conId", contract)
    cd = ib.get_contract_details(contract)[0]
    print("contract.conId", cd)

    account = Account.objects.get(uid=ib.account_id)
    instrument = Contract.objects.get(conid=cd.contract.conId)

    print("instrument", instrument)

    oid = ib.nextValidOrderId
    ib.nextValidOrderId += 1

    stop_price = Decimal(data.get("stop_price"))

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

    # ib_order.orderType = "MKT"
    # order = Order.market_order(account, instrument, side, abs(amount))

    ib_order.orderType = "STP LMT"
    ib_order.outsideRth = True
    ib_order.auxPrice = stop_price
    if ib_order.action == "BUY":
        ib_order.lmtPrice = stop_price + Decimal(0.25)
    else:
        ib_order.lmtPrice = stop_price - Decimal(0.25)
    order = Order.stop_order(account, instrument, side, abs(amount))

    cprint(f"ib_order: {ib_order}", "blue")

    # создать ордер в базе данных
    order.local_id = local_id
    order.save()

    ib.placeOrder(oid, contract, ib_order)

    order.status = "Sent"
    order.save(update_fields=["status"])


def update_order(ib, data):
    local_id = data.get("local_id")
    stop_price = Decimal(data.get("stop_price"))

    for ib_order, contract, orderState in ib._orders_by_pid.values():
        if ib_order.orderRef == local_id:
            cprint(f"ib_order: {ib_order} {orderState.status}", "blue")
            ib_order.auxPrice = stop_price
            if ib_order.action == "BUY":
                ib_order.lmtPrice = stop_price + Decimal(0.25)
            else:
                ib_order.lmtPrice = stop_price - Decimal(0.25)
            ib.placeOrder(ib_order.orderId, contract, ib_order)

            return

    log.error(f"Order not found: {data}")


def cancel_order(ib, data):
    local_id = data.get("local_id")

    inactive = ["Filled", "Cancelled", "ApiCancelled", "Inactive"]

    # FIXME: _orders_by_pid обновляется в openOrder и не ловит состояние canceled
    for ib_order, contract, orderState in ib._orders_by_pid.values():
        if ib_order.orderRef == local_id and orderState.status not in inactive:
            cprint(f"ib_order: {ib_order} {orderState.status}", "blue")
            ib.cancelOrder(ib_order.orderId, "")
            return

    log.error(f"Order not found: {data}")


##################


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
                cprint(f"New Trade: {exec}", "green")
                trades_to_create.append(Trade.from_ib(exec, account, order))
                updated_orders.append(order)
            else:
                log.error(f"Execution without order: {exec.execId}, o: {exec.permId}")

    if trades_to_create:
        Trade.objects.bulk_create(trades_to_create)

        action = {"types": ["trade"]}
        a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"Redis sync-message: {action}, {a}")

    # Пересчитать цены ордеров, для которых загружены сделки.
    # updated_orders
    # Получить сделки для этих ордеров, посчитать, сохранить.
    # trades = Trade.objects.filter(account=account)


def orderStatus(
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

    av_fill_price = avgFillPrice if avgFillPrice < 10**10 else None

    if permId and permId in APP._orders_by_pid:
        # TODO: для активного ордера проверить время его получения
        order, contract, state = APP._orders_by_pid[permId]
    else:
        log.error(f"Order not found, {permId}")
        return

    cprint(
        f"OrderStatus: oId: {orderId}, pId: {permId}, status: {state.status} >> {status}, "
        f"fill_pr: {av_fill_price}, filled: {filled}, remaining: {remaining}, "
        f"price: {order.lmtPrice}, held: {whyHeld}",
        "red",
    )

    # Обновление статуса ордера в кэше
    state.status = status
    APP._orders_by_pid[permId] = order, contract, state

    # TODO: закешировать?
    account = Account.objects.get(uid=order.account)

    with transaction.atomic():
        # Контракт достается из базы или создается
        try:
            db_contract = Contract.objects.get(conid=contract.conId)
        except Contract.DoesNotExist:
            log.warn(f"Create new contract {contract.conId}")
            db_contract = Contract.from_ib(contract)
            db_contract.save()

        try:
            # Два варианта:
            # - ордер создан на стороне IB, мы сразу знаем permId
            # - ордер создан через базу и лежит там без permId
            # Про ref нужно понимать, что чужие ref могут быть не уникальными.
            # Если в ref лежит наш идентификатор, то нужно сначала искать ордер
            # в базе по нему. Если не нашлось, то поискать по permId.

            cprint(f"Order: perm: {order.permId}, ref: {order.orderRef}", "yellow")

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

        except Order.DoesNotExist:
            # Если ордера всё еще нет в базе - создать
            db_order = Order.from_ib(order, account, db_contract, state)

        log.info(f"Order in DB {db_order}")

        # Используется последнее известное значение позиции контракта
        try:
            known_ib_position, avg_price = APP._positions_by_conid[contract.conId]
        except KeyError:
            known_ib_position, avg_price = 0, None

        # Редактирование или создание позиции
        try:
            # TODO: не редактировать, если не было изменений
            # orderStatus возникает при редактировании цены ордера,
            # поэтому часто это не связано с изменением позиции.
            db_position = Position.objects.get(account=account, contract=db_contract)
            if db_position.amount != known_ib_position:
                cprint(f"Pos: {db_position.amount} -> {known_ib_position}", "green")
                db_position.amount = known_ib_position
                db_position.avg_price = avg_price
                db_position.save()
        except Position.DoesNotExist:
            cprint(f"Pos NEW: {known_ib_position}", "green")
            db_position = Position.from_ib(
                account, db_contract, known_ib_position, avg_price
            )
            db_position.save()

        db_order.avg_fill_price = av_fill_price
        db_order.filled = filled
        db_order.status = status
        db_order.save()

        action = {"types": ["order", "position"]}
        a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"Redis sync-message: {action}, {a}")


def initial_sync(ib):
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

    log.info(f"Start initial_sync, account: {ib.account_id}")

    account = Account.objects.get(uid=ib.account_id)

    positions = Position.objects.filter(account=account)
    positions_by_con_id = {p.contract.conid: p for p in positions}

    orders = Order.objects.filter(account=account)
    orders_by_id = {o.order_id: o for o in orders}

    contracts = Contract.objects.all()
    contracts_by_id = {c.conid: c for c in contracts}

    # Получить данные из IB

    ib_orders = ib.get_orders()
    ib_positions = ib.get_positions()
    ib_executions = ib.get_executions()

    ############
    # Создаются контракты, которых не было в базе

    contracts_to_create = []
    all_contracts = [r[0] for r in ib_orders] + [r[1] for r in ib_positions]

    for contract in all_contracts:
        if contract.conId not in contracts_by_id:
            c = Contract.from_ib(contract)
            contracts_by_id[contract.conId] = c
            contracts_to_create.append(c)
            log.info(f"Create contract: {c.local_symbol} // {c.conid}")

    Contract.objects.bulk_create(contracts_to_create)

    ############
    # Ордеры

    orders_to_create = []

    for contract, order, state in ib_orders:
        # print("IB ORDER", order, ">", order.orderRef, state.status)

        if order.permId:
            if order.permId not in orders_by_id:
                c = contracts_by_id[contract.conId]
                orders_to_create.append(Order.from_ib(order, account, c, state))
            else:
                # TODO: проверить изменения ордеров из базы, которые не в финальном состоянии
                # FIXME: сделать нормально
                db_order = orders_by_id[order.permId]
                if state.status != db_order.status:
                    cprint(f"UPDATE in DB {order} {orders_by_id[order.permId]}", "magenta")
                    db_order.status = state.status
                    db_order.save(update_fields=["status"])

    if orders_to_create:
        Order.objects.bulk_create(orders_to_create)

        action = {"types": ["order"]}
        a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"Redis sync-message: {action}, {a}")

    ############
    # Позиции

    positions_to_create = []

    # Всем обнуляю значения, но пока не сохраняю
    for _, position in positions_by_con_id.items():
        position.amount = 0
        position.avg_price = None
        # position.unrealized_pnl = None

    for acnt, con, pos, avgCost in ib_positions:
        c = contracts_by_id[con.conId]

        if acnt != account.uid:
            log.warn(f"Skip wrong account: {acnt}")
            continue

        avg_price = avgCost / int(c.multiplier)  # * 100  # ???

        if con.conId in positions_by_con_id:
            # update position
            position = positions_by_con_id[con.conId]
            position.avg_price = avg_price
            position.amount = pos
        else:
            # create position
            positions_to_create.append(Position.from_ib(account, c, pos, avg_price))

    positions_to_update = positions_by_con_id.values()

    if positions_to_create or positions_to_update:
        Position.objects.bulk_create(positions_to_create)
        Position.objects.bulk_update(positions_to_update, ["avg_price", "amount"])

        action = {"types": ["position"]}
        a = redis_client.publish(SYNC_CHANNEL, json.dumps(action, default=str))
        log.info(f"Redis sync-message: {action}, {a}")

    log.info("Check initial_sync")

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


class Command(BaseCommand):
    """
    Синхронизация состояния базы с IB через TWS.
    """

    def add_arguments(self, parser):
        parser.add_argument("--config", type=str, dest="config", default=DEF_CONFIG)

    def handle(self, **kwargs):
        app = None
        thread = None

        pubsub.subscribe("BOT_ACTIONS")

        try:
            while True:
                go = datetime.now().second % 10 == 0
                go_2 = datetime.now().second % 13 == 0

                # Обработка команд от бота: создание и редактирование ордеров
                try:
                    message = pubsub.get_message(timeout=0.1)
                    if message and message.get("type") == "message":
                        process_bot_action(app, message)
                except Exception as e:
                    log.error(f"Redis pubsub get_message error: {e}")
                    log.exception(e)
                    pass

                # регулярные запросы
                if go_2 and app and app.isConnected():
                    try:
                        get_executions(app)
                    except Exception as e:
                        log.error(f"Get executions error: {e}")

                    time.sleep(1)

                # Переконнект
                if not app or go and not app.isConnected():
                    app = IBSync()
                    # TODO: брать из настроек
                    app.connect("127.0.0.1", 7497, 0)

                    log.info(f"Server Version: {app.decoder.serverVersion}")

                    global APP
                    APP = app

                    if thread:
                        try:
                            thread.join()
                        except:
                            raise

                    # Endless message loop
                    thread = IBThread(app)
                    thread.start()

                    # Не соединилось, попробовать еще раз
                    if not app.isConnected():
                        time.sleep(1)
                        continue

                    # Check if the API is connected via orderid
                    while True:
                        if isinstance(app.nextValidOrderId, int):
                            cprint(f"Connected", "green")
                            break
                        time.sleep(0.5)

                    # Синхронизация базы с IB
                    while True:
                        try:
                            with transaction.atomic():
                                initial_sync(app)
                                break
                        except Exception as e:
                            log.error(f"Initial sync error: {e}")
                            log.exception(e)
                            time.sleep(3)

                    # Начать real-time обработку сообщений orderStatus
                    app.orderStatus = orderStatus

                    app.pnl = pnl
                    app.updatePortfolio = updatePortfolio

                    # Нет ничего про профит, поэтому все равно придется брать AccountUpdates
                    # ib.reqAccountSummary(ib.r_id, "All", "NetLiquidation,InitMarginReq")
                    # time.sleep(0.1)

                    # С этой хренью новые ордеры из TWS получают id от данного клиента.
                    # Работает только для подключения с ClientId = 0.
                    # Пока непонятно, что с ордерами из мобильного приложения, например.
                    app.reqAutoOpenOrders(True)
                    time.sleep(0.1)

                    # это подписка, но её нельзя отменить
                    app.reqAccountUpdates(True, app.account_id)
                    time.sleep(0.1)

                    # На это нельзя подписываться много раз, заебет.
                    # Но при одной подписке оно реально приходит на каждое изменение.
                    # Выглядит удобно.
                    app.reqPnL(app.r_id, app.account_id, "")
                    time.sleep(0.1)

                    # Получить исторические сделки, посчитать av_fill_price
                    try:
                        get_executions(app)
                    except Exception as e:
                        log.error(f"Get executions error: {e}")

                    time.sleep(1)

                time.sleep(0.5)

        except (KeyboardInterrupt, SystemExit):
            print()
            log.info("Stop\n")

        finally:
            if app:
                app.disconnect()
