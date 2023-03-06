import argparse
import yaml
import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from ibkr_api.client import IBClient, IBThread, StockContract
from ibkr_api.ib_sync import IBSync
import time
from termcolor import cprint
import json
from decimal import Decimal
from main.models import Account, Position, Order, Trade, Contract
from django.db import transaction
from ibapi.order import Order as IBOrder
from django.core.cache import cache
import redis

# Логгер для этого файла
log = logging.getLogger("sync")


DEF_CONFIG = "../config/bot.yaml"

APP = None

BOT_ID_PREFIX = "bot_"

"""
Важные ошибки, которые нужно обработать:
ERROR 1100 Connectivity between IB and Trader Workstation has been lost.
ERROR 1102 Connectivity between IB and Trader Workstation has been restored...
"""


# динамически ловить commissionReport и/или execDetails?
# Проблема в том, что execDetails приходят через раз.
# Думаю, правильный выход такой: нужно после исполнения ордера запускать
# несколько синхронных запросов, которые будут забирать все execDetails.
# Допустим, через секунду после исполнения и через 10 секунд.
# Но не чаще, чем раз в 3 секунды, допустим. Если запрос уже недавно был,
# то следующий сдвигается вперед. Ну или типа того.



def pnl(reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float):
    account = Account.objects.get(uid=APP.account_id)
    values = APP.values[account.uid]
    
    account.daily_pnl = dailyPnL 
    account.unrealized_pnl = unrealizedPnL
    account.realized_pnl = realizedPnL

    # TODO добавить Cushion — Excess liquidity as a percentage of net liquidation value
    
    # FIXME KeyError: 'NetLiquidation'; pnl может приходить раньше values.

    account.net_value = values["NetLiquidation"]
    account.margin_used = values["MaintMarginReq"]
    account.cash_value = values["CashBalance"]
    account.ex_liq_sec = values["ExcessLiquidity-S"]
    account.ex_liq_com = values["ExcessLiquidity-C"]

    account.save()


def updatePortfolio(contract, amount, marketPrice, marketValue, averageCost, 
        unrealizedPNL, realizedPNL, accountName):

    account = Account.objects.get(uid=accountName)
    position = Position.objects.get(account=account, contract__conid=contract.conId)

    if position.amount != amount:
        log.error(f"Position missmatch: db = {position.amount}, ib = {amount}")

    position.avg_price = averageCost
    position.unrealized_pnl = unrealizedPNL
    position.save(update_fields=["avg_price", "unrealized_pnl"])
    


def check_new_orders(ib):

    account = Account.objects.get(uid=ib.account_id)
    new_orders = Order.objects.filter(account=account, status="New")
    
    for no in new_orders:
        no.status = "Sending"
        no.save()

        # ib.reqIds(-1)
        # time.sleep(0.5)
        
        oid = ib.nextValidOrderId
        ib.nextValidOrderId += 1

        contract = StockContract("AAPL")

        # Create limit order object
        order = IBOrder()
        order.action = no.action 
        order.totalQuantity = no.amount
        order.orderType = "LMT"
        order.lmtPrice = no.limit_price
        order.eTradeOnly       = False
        order.firmQuoteOnly    = False
        # order.orderRef = '{"id": "%s", "dt": "2023-02-28"}' % no.local_id
        order.orderRef = no.local_id
        order.outsideRth = no.outside_rth

        ib.placeOrder(oid, contract, order)
        # ib.reqCurrentTime()

        time.sleep(1)


def update_order(ib):
    order_id = 1793050531  #  1793050442 | 1793050531

    # self.cancelOrder(self.simplePlaceOid, "")

    ib_order, contract, orderState = ib._orders_by_pid[order_id]
    cprint(f"ib_order: {ib_order}", "blue")

    oid = ib_order.orderId
    ib_order.lmtPrice = ib_order.lmtPrice - 0.1

    ib.placeOrder(oid, contract, ib_order)


def get_executions(ib):

    account = Account.objects.get(uid=ib.account_id)

    # TODO выбрать только последние пару дней
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

    Trade.objects.bulk_create(trades_to_create)

    # Пересчитать цены ордеров, для которых загружены сделки.
    # updated_orders
    # Получить сделки для этих ордеров, посчитать, сохранить.
    # trades = Trade.objects.filter(account=account)



# TWS Account Window
# reqAccountUpdates(True, account) - sub. for the account and portfolio info
# unless there is a position change this information is updated every three minutes
#       updateAccountValue
#       updatePortfolio
#       updateAccountTime

# TWS Account Summary window
# reqAccountSummary - subscription for the account data
#       accountSummary

# Эта подписка есть в любом случае.
# reqPositions()
# Subscribes to position updates for all accessible accounts.

# PnL для всего аккаунта
# reqPnL(17001, "DU111519", "")
#       pnl



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
        # TODO для активного ордера проверить время его получения
        order, contract, state = APP._orders_by_pid[permId]
    else:
        log.error(f"Order not found, {permId}")
        return

    cprint(
        f"OrderStatus: oId: {orderId}, pId: {permId}, status: {status}, "
        f"fill_pr: {av_fill_price}, filled: {filled}, remaining: {remaining}, "
        f"price: {order.lmtPrice}, held: {whyHeld}",
        "magenta",
    )

    # TODO закешировать?
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
    # TODO проверить изменения ордеров из базы, которые не в финальном состоянии

    orders_to_create = []

    for contract, order, state in ib_orders:
        
        print("IB ORDER", order, ">", order.goodAfterTime)

        if order.permId and order.permId not in orders_by_id:
            c = contracts_by_id[contract.conId]
            orders_to_create.append(Order.from_ib(order, account, c, state))

    Order.objects.bulk_create(orders_to_create)

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

    Position.objects.bulk_create(positions_to_create)
    Position.objects.bulk_update(positions_to_update, ["avg_price", "amount"])

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

        redis_client = redis.Redis()
        pubsub = redis_client.pubsub()

        pubsub.subscribe("BOT_ACTIONS")

        try:
            while True:
                go = datetime.now().second % 10 == 0
                go_2 = datetime.now().second % 13 == 0

                # Обработка команд от бота: создание и редактирование ордеров
                try:
                    message = pubsub.get_message(timeout=0.1)
                    if message:
                        cprint(f"REDIS: {message}", "red")
                        update_order(app)
                except Exception as e:
                    # log.error(f"Redis pubsub get_message error: {e}")
                    pass

                # отправка новых запросов из БД в IB
                if app and app.isConnected():
                    cache.set('last_connected', str(datetime.now()), 300)
                    check_new_orders(app)

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
            app and app.disconnect()
