import json
import logging
import threading
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from posixpath import abspath
from time import monotonic, sleep

import redis
import yaml
from django.core.management.base import BaseCommand
from django.db import transaction
from ib_sync import IBSync, IBThread
from ibapi.order import Order as IBOrder
from termcolor import colored, cprint

from main.models import Account, Contract, Order, Position, Trade
from project.helpers.alert import TgAlert

# Логгер для этого файла
log = logging.getLogger("sync")
log.setLevel(logging.INFO)

# loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
# for logger in loggers:
#     logger.setLevel(logging.DEBUG)

# logging.getLogger("ibapi.connection").setLevel(logging.DEBUG)
# logging.getLogger("ibapi.client").setLevel(logging.INFO)


DEF_CONFIG = "../config/bot.yaml"

BOT_ID_PREFIX = "bot_"

SYNC_CHANNEL = "SYNC"

DT_FMT = "%Y-%m-%d %H:%M:%S"


class FatalException(Exception):
    """
    Ошибка, после которой нужен переконнект.
    """

    pass


def is_redis_available(r):
    try:
        r.ping()
    except Exception:
        return False
    return True


############################


class IBSyncExtended(IBSync):
    def __init__(self, redis_client, tg_alert):
        super().__init__()
        self.tg = tg_alert
        self.redis_client = redis_client
        self.lock_for_sync = False  # запрет обработки событий до синхронизации базы
        self.connections = {
            "tws": "disconnected",
            "ibkr": "",
        }
        self.request = {}  # request data by r_id
        self.response_dt = datetime.min

        # Время последнего появления различных событий
        self.prev_time = defaultdict(float)

    def managedAccounts(self, accountsList: str):
        super().managedAccounts(accountsList)
        self.connections["tws"] = "connected"
        self.response_dt = datetime.utcnow()

    def currentTime(self, time):
        super().currentTime(time)
        self.connections["tws"] = "connected"
        self.response_dt = datetime.utcnow()

    def connectionClosed(self):
        super().connectionClosed()
        # Все подписки сбрасываются, когда соединение закрывается
        self.connections["tws"] = "disconnected"
        # for r_id, sub in self.request.items():
        #     if not sub.get("cancelled"):
        #         log.error(f"Subscription cancelled: {r_id} {sub['sid']}")
        #         self.request[r_id]["cancelled"] = True

    #####
    # Обработка событий с обновлениями данных

    def pnl(
        self, reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float
    ):
        if self.lock_for_sync:
            return

        self.prev_time["pnl"] = monotonic()

        log.debug(
            f"PNL event, r_id: {reqId}, update account, "
            f"unrealizedPnL: {unrealizedPnL:+0.2f} "
        )

        account = Account.objects.get(uid=self.account_id)
        values = self.values[account.uid]

        account.daily_pnl = Decimal(dailyPnL)
        account.unrealized_pnl = Decimal(unrealizedPnL)
        account.realized_pnl = Decimal(realizedPnL)

        if "NetLiquidation" not in values:
            log.error("NetLiquidation wasn't received yet")
            return

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

        self.prev_time["updatePortfolio"] = monotonic()

        account = Account.objects.get(uid=accountName)

        sid = self.sid_for_contract(contract)

        log.info(colored(f"updatePortfolio: {sid} {position}", "cyan"))

        db_position = Position.objects.get(account=account, contract__sid=sid)

        if db_position.amount != position:
            log.error(f"Position missmatch: db = {db_position.amount}, ib = {position}")

        # FIXME: нужно чтобы SYNC с разными client_id получали все ордеры

        # Или хрен с ним, пусть пишет в базу position?
        # db_position.amount = position

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

    def openOrder(self, orderId, contract, order, orderState):
        """
        Всё нужное уже делается в IBSync, здесь только log и тайминг.
        """
        super().openOrder(orderId, contract, order, orderState)
        self.prev_time["openOrder"] = monotonic()
        log.debug(colored(f"openOrder: {order}, {orderState.status}", "yellow"))

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

        self.prev_time["orderStatus"] = monotonic()

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
                    f"OrderStatus: oId: {orderId}, clientId: {clientId}, "
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
            pos_amount_changed = False
            try:
                # TODO: не редактировать, если не было изменений
                # orderStatus возникает при редактировании цены ордера,
                # поэтому часто это не связано с изменением позиции.
                db_position = Position.objects.get(
                    account=account, contract=db_contract
                )
                if db_position.amount != known_ib_position:
                    pos_amount_changed = True
                    log.info(f"Pos, DB: {db_position.amount}, IB: {known_ib_position}")
                    db_position.amount = known_ib_position
                    db_position.avg_price = avg_price
                    db_position.save()
            except Position.DoesNotExist:
                pos_amount_changed = True
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

            # После всего важного (блокирующий запрос)
            if pos_amount_changed:
                self.tg.message(f"Position {sid} {db_position.amount}")

    def updateAccountTime(self, *args, **kwargs):
        super().updateAccountTime(*args, **kwargs)
        self.prev_time["updateAccountTime"] = monotonic()
        log.debug(f"updateAccountTime: {args}")

    def updateAccountValue(self, *args, **kwargs):
        super().updateAccountValue(*args, **kwargs)
        self.prev_time["updateAccountValue"] = monotonic()
        # log.debug(f"updateAccountValue: {args}")

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

    def place_test_order(self) -> None:
        """
        Создается whatIf ордер, чтобы проверить openOrder callback.
        """
        oid = self.nextValidOrderId
        self.nextValidOrderId += 1

        contract = self.contract_for_sid("ARCA_SPY")

        order = IBOrder()
        order.orderId = oid
        order.action = "BUY"
        order.totalQuantity = Decimal(1)
        order.orderType = "LMT"
        order.lmtPrice = 100
        order.whatIf = True

        contract, order_res, orderState = self.place_order(contract, order)

        log.debug(f"WTF order: {order_res} | Status: {orderState.status}")

    def create_order(self, data):
        """
        Создание ордера в IB
        """
        # ib_contract - нужен для отправки ордера в IB
        # db_contract - нужен для сохранения ордера в базе

        sid = data["sid"]

        ib_contract = self.contract_for_sid(sid)

        db_account = Account.objects.get(uid=self.account_id)

        # Контракта может не быть в базе
        try:
            db_contract = Contract.objects.get(sid=sid)
        except:
            # Получить контракт из IBKR, сохранить в базе
            log.info(f"Create contract: {sid}")
            cd = self.get_contract_details(ib_contract)[0]
            db_contract = Contract.from_ib(ib_contract, cd, sid)
            db_contract.save()

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

        ib_order.orderType = "MKT"
        db_order = Order.market_order(db_account, db_contract, side, abs(amount))

        # ib_order.orderType = "STP LMT"
        # ib_order.outsideRth = True
        # ib_order.auxPrice = stop_price
        # if ib_order.action == "BUY":
        #     ib_order.lmtPrice = stop_price + 0.25
        # else:
        #     ib_order.lmtPrice = stop_price - 0.25
        #
        # db_order = Order.stop_order(db_account, db_contract, side, abs(amount))

        log.info(colored(f"Create, ib_order: {ib_order}", "green"))

        # создать ордер в базе данных
        db_order.local_id = local_id
        db_order.save()

        self.placeOrder(oid, ib_contract, ib_order)

        self.tg.message(f"Create order: {sid} {amount:+f}")

        db_order.status = "Sent"
        db_order.save(update_fields=["status"])

    def update_order(self, data):
        """
        Редактирование ордера в IB
        """
        log.info(colored(f"Update, data: {data}", "yellow"))

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
                sid = self.sid_for_contract(contract)
                log.info(colored(f"Cancel, ib_order: {ib_order}", "magenta"))
                self.cancelOrder(ib_order.orderId, "")
                self.tg.message(f"Cancel order: {sid} {ib_order}")
                return

        log.error(f"Order not found: {data}")


############################


class Sync:
    def __init__(self, config: dict) -> None:
        self.redis_config = config.get("redis", {})
        self.gateway = config.get("gateway", {})
        self.running = True

        self.tg = TgAlert(config.get("telegram", {}))

        # Отметки, когда что произошло
        self.request_time = datetime.min
        self.prev_executions = monotonic()
        self.prev_subscribe = monotonic()
        self.prev_test_order = monotonic()

        self.gw_client_id = self.gateway.get("sync_client_id", 0)

        self.tg.message("Start Sync")

        log.info(colored("Start Sync ⋅ﾐ(•ᵕ•)ﾉ", "magenta"))
        log.info(f"Gateway: {self.gateway}")
        log.info(f"Redis: {self.redis_config}")

        self.rc = redis.Redis(**dict(self.redis_config))
        self.ib = IBSyncExtended(self.rc, self.tg)

        self.pubsub = self.rc.pubsub()
        self.pubsub.subscribe("BOT_ACTIONS")

        # FIXME:
        self.pnl_r_id = 0

    def request_tws_time(self) -> None:
        self.request_time = datetime.utcnow()
        self.ib.reqCurrentTime()

    def redis_publish(self, action: dict) -> None:
        json_str = json.dumps(action, default=str)
        a = self.rc.publish(SYNC_CHANNEL, json_str)
        log.info(f"To Redis: {json_str}, {a}")

    def is_delayed(self, event: str, max_delay: int) -> bool:
        """
        Проверка задержки данного типа события и алерт.
        """
        delay = monotonic() - self.ib.prev_time[event]
        if delay > max_delay:
            log.error(f"Event {event} delay: {delay:0.2f} > {max_delay}")
            return True
        return False

    def maintain_subscriptions(self, force=False) -> None:
        """
        Подписка на то, что давно не приходило.
        """

        ########################################
        # Подписка на orderStatus и openOrder
        # Проверяю openOrder, т.к. orderStatus не подергать руками

        if force or self.is_delayed("openOrder", 120):
            self.ib.prev_time["openOrder"] = monotonic()

            if self.gw_client_id == 0:
                # С AutoBind новые ордеры из TWS получают id от данного клиента.
                # Работает только для подключения с ClientId = 0.
                self.ib.reqAutoOpenOrders(bAutoBind=True)
            else:
                log.warning(colored("Client ID != 0, no AutoBind", attrs=["bold"]))
                self.ib.reqOpenOrders()

            sleep(0.1)

        ########################################
        # Подписка на всякое (отменить нельзя):
        # updateAccountValue
        # updateAccountTime
        # updatePortfolio

        # Считаю, что если updateAccountTime приходит, значит всё OK
        d_1 = force or self.is_delayed("updateAccountValue", 300)
        d_2 = force or self.is_delayed("updateAccountTime", 200)
        d_3 = force or self.is_delayed("updatePortfolio", 1800)

        if d_1 or d_2 or d_3:
            self.ib.prev_time["updateAccountValue"] = monotonic()
            self.ib.prev_time["updateAccountTime"] = monotonic()
            self.ib.prev_time["updatePortfolio"] = monotonic()
            self.ib.reqAccountUpdates(True, self.ib.account_id)
            sleep(0.1)

        ########################################
        # Подписка на PnL

        if force or self.is_delayed("pnl", 200):
            self.ib.prev_time["pnl"] = monotonic()

            if self.pnl_r_id:
                self.ib.cancelPnL(self.pnl_r_id)
                self.pnl_r_id = 0
                sleep(0.1)

            # На это нельзя подписываться много раз, заебет.
            self.pnl_r_id = self.ib.r_id
            self.ib.reqPnL(self.pnl_r_id, self.ib.account_id, "")
            sleep(0.1)

    def get_executions(self) -> None:
        ib: IBSyncExtended = self.ib
        account = Account.objects.get(uid=ib.account_id)

        # FIXME: выбрать только последние пару дней
        trades = Trade.objects.filter(account=account).order_by("id")[:1000]
        trades_by_exec_id = {t.exec_id: t for t in trades}

        # FIXME: выбрать только последние пару дней
        orders = Order.objects.filter(account=account).order_by("id")[:500]
        orders_by_id = {o.order_id: o for o in orders}

        executions = ib.get_executions()

        trades_to_create = []
        updated_orders = []

        for _, exec in executions:
            if exec.execId in trades_by_exec_id:
                continue

            if order := orders_by_id.get(exec.permId):
                log.info(colored("New trade: " + f"{exec}"[-120:], "cyan"))
                trades_to_create.append(Trade.from_ib(exec, account, order))
                updated_orders.append(order)
            else:
                log.error(
                    f"Execution without order: {exec.execId}, "
                    f"order.perm_id: {exec.permId}, "
                    f"client_id: order={exec.clientId} sync={self.gw_client_id}"
                )
                if self.gw_client_id != 0:
                    pass
                    # TODO: resync orders (+ contracts)

        if trades_to_create:
            Trade.objects.bulk_create(trades_to_create)
            self.redis_publish({"types": ["trade"]})

        # Бывает так, что событие ордера не было поймано вовремя.
        # Тогда среднюю цену можно восстановить только по сделкам.
        for order in orders:
            # Если ордер исполнен (хотя бы частично), но нет средней цены,
            # значит ордер создан при инициализации, где нет этих данных.
            if order.filled and not order.avg_fill_price:
                total_value = Decimal(0)
                total_amount = Decimal(0)
                for trade in Trade.objects.filter(order=order):
                    total_value += trade.amount * trade.price
                    total_amount += trade.amount
                if total_amount > 0:
                    av_price = total_value / total_amount
                    order.avg_fill_price = av_price
                    order.save(update_fields=["avg_fill_price"])
                    log.info(f"Update avg_fill_price, order: {order}")

    def get_new_contracts(self, contracts_by_sid, uniq_contracts) -> list:
        """
        Новые контракты для добавления в базу данных.
        """
        ib: IBSyncExtended = self.ib
        contracts_to_create = []
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
        return contracts_to_create

    def sync_orders(self, account, contracts_by_sid, ib_orders):
        """
        Создать в базе новые ордеры из IB, обновить старые.
        """

        orders = Order.objects.filter(account=account)
        orders_by_id = {o.order_id: o for o in orders}

        orders_to_create = []

        for contract, order, state in ib_orders:
            # log.info(
            #     f"IB ORDER {order} > {order.orderRef}, "
            #     f"tq:{order.totalQuantity}, {state.status}"
            # )

            if not order.permId:
                continue

            if db_order := orders_by_id.get(order.permId):
                # FIXME: сделать нормально
                # проверить изменения ордеров из базы,
                # которые не финализированы
                if state.status != db_order.status:
                    msg = f"UPDATE in DB {order} {db_order}"
                    log.info(colored(msg, "magenta"))
                    db_order.status = state.status
                    db_order.save(update_fields=["status"])
            else:
                # Создание ордера в базе
                sid = self.ib.sid_for_contract(contract)
                db_c = contracts_by_sid[sid]
                db_order = Order.from_ib(order, account, db_c, state)
                orders_to_create.append(db_order)

        if orders_to_create:
            Order.objects.bulk_create(orders_to_create)

    def initial_sync(self) -> None:
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
        txt = f"Start initial_sync, account: {self.ib.account_id}"
        log.info(colored(txt, attrs=["bold"]))

        # Получить данные из базы
        account = Account.objects.get(uid=self.ib.account_id)

        positions = Position.objects.filter(account=account)
        positions_by_sid = {p.contract.sid: p for p in positions}

        contracts = Contract.objects.all()
        contracts_by_sid = {c.sid: c for c in contracts}

        # Получить данные из IB
        ib_orders = self.ib.get_orders()
        ib_positions = self.ib.get_positions()
        ib_executions = self.ib.get_executions()

        # Все контракты из данных IB
        all_contracts = [r[0] for r in ib_orders]
        all_contracts += [r[1] for r in ib_positions]
        all_contracts += [r[0] for r in ib_executions]
        uniq_contracts = {c.conId: c for c in all_contracts}

        # Создаются неизвестные контракты
        new_contracts = self.get_new_contracts(contracts_by_sid, uniq_contracts)
        Contract.objects.bulk_create(new_contracts)

        ############
        # Ордеры
        self.sync_orders(account, contracts_by_sid, ib_orders)

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
            sid = self.ib.sid_for_contract(contract)

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

        # Проверить, что данные в IB не изменились с момента получения
        log.info("Check initial_sync integrity")

        ib_orders_2 = self.ib.get_orders()
        ib_positions_2 = self.ib.get_positions()
        ib_executions_2 = self.ib.get_executions()

        # Сравнить данные ib_* и ib_*_2.
        # Если одинаковые, то всё ok.
        if len(ib_orders) != len(ib_orders_2):
            raise Exception("Orders updated")

        if len(ib_positions) != len(ib_positions_2):
            raise Exception("Positions updated")

        if len(ib_executions) != len(ib_executions_2):
            raise Exception("Executions updated")

    def check_tws_health(self) -> None:
        """
        Проверка статуса подписок и задержки прихода данных.
        """

        # Проверить синхронизацию времени
        time_diff = abs((self.request_time - self.ib.tws_time).total_seconds())
        if time_diff > 100:
            log.error(f"TWS time out of sync: {time_diff:0.2f} sec")
        elif time_diff > 10:
            log.warning(f"TWS time out of sync: {time_diff:0.2f} sec")

        if not self.ib.isConnected():
            raise FatalException("tws_disconnected")

        # Проверить, когда от TWS последний раз приходил ответ
        response_gap = (datetime.utcnow() - self.ib.response_dt).total_seconds()
        if response_gap > 100:
            raise FatalException("tws_delay")
        elif response_gap > 20:  # сильно больше, чем период maintain
            log.warning(f"Large TWS response gap: {response_gap:0.2f} sec")

    def periodic_actions(self) -> None:
        """
        Операции, которые нужно постоянно повторять
        """
        # Проверка связи с Redis
        if not is_redis_available(self.rc):
            log.error(f"Redis in unavailable")
            sleep(5)
            return

        # Обработка команд от бота
        if self.ib and self.ib.isConnected():
            try:
                message = self.pubsub.get_message(timeout=0.1)
                if message and message.get("type") == "message":
                    self.ib.process_bot_action(message)
            except Exception as e:
                log.error(f"Redis pubsub get_message error: {e}")
                log.exception(e)
                pass

        if not self.ib.isConnected():
            raise FatalException("tws_disconnected")

        # Регулярно двигать ордер, чтобы работала
        # проверка задержки событий orderStatus
        if monotonic() - self.prev_test_order > 60:
            self.prev_test_order = monotonic()
            self.ib.place_test_order()

        # Проверки соединения и задержки ответов TWS
        if monotonic() - self.prev_maintain > 5:
            self.prev_maintain = monotonic()
            self.check_tws_health()
            # Новый запрос времени
            self.request_tws_time()

        # Получить executions
        if monotonic() - self.prev_executions > 13:
            self.prev_executions = monotonic()
            self.get_executions()

        # Переподписка, если что-то отвалилось
        if monotonic() - self.prev_subscribe > 30:
            self.prev_subscribe = monotonic()
            self.maintain_subscriptions()

    def run(self) -> None:
        """
        Бесконечный цикл, в котором поддерживаются нужные
        соединения с TWS/GW и нужные подписки на данные.
        """
        while not sleep(0.1) and self.running:
            # Попытка дисконнекта, если есть чего
            try:
                if self.ib:
                    self.ib.disconnect()
            except Exception as e:
                log.error(f"TWS disconnect exception: {e}")

            # Подключение к TWS
            try:
                host = self.gateway["host"]
                port = self.gateway["port"]
                self.ib.tws_time = datetime.min
                self.ib.connect(host, port, self.gw_client_id)
                # Обработка событий блокируется до завершения initial_sync
                self.ib.lock_for_sync = True
            except Exception as e:
                log.error(f"TWS connect exception: {e}")
                log.exception(e)
                self.ib.disconnect()
                sleep(5)
                continue

            # Если соединение есть, но отваливается, значит client_id занят
            if self.ib.isConnected():
                dt = monotonic()
                while not sleep(0.2) and monotonic() - dt < 2:
                    if not self.ib.isConnected():
                        log.error(f"Possibly client_id conflict: {self.gw_client_id}")
                        break

            # Если TWS не запущен или в процессе перезапуска,
            # isConnected вернет false. Повторить попытку через N секунд
            if not self.ib.isConnected():
                log.error("No TWS connection, reconnect in 20 sec")
                sleep(20)
                continue

            # Поток обработки входящих сообщений
            try:
                IBThread(self.ib).start()
            except Exception as e:
                log.exception(e)
                log.error("IBThread exception, reconnect in 5 sec")
                sleep(5)
                continue

            # You have to make sure the connection has been fully established
            # before attempting to do any requests to the TWS.
            # Failure to do so will result in the TWS closing the connection.
            dt = monotonic()
            while not sleep(0.2) and monotonic() - dt < 5:
                if self.ib.nextValidOrderId > 0:
                    log.info(f"TWS is connected, order id: {self.ib.nextValidOrderId}")
                    break

            # Если не дождались - переконнект
            if not self.ib.nextValidOrderId > 0:
                log.error("No TWS connection, no Next Order ID, reconnect now")
                continue

            # В этом месте должно быть активное подключение
            self.request_tws_time()

            # После соединения происходит синхронизация базы с IB
            while True:
                self.ib.lock_for_sync = True
                try:
                    with transaction.atomic():
                        self.initial_sync()
                        # Уведомление после успешной синхронизации
                        self.redis_publish({"types": ["initial_sync"]})
                        break
                except Exception as e:
                    log.error(f"Initial sync error: {e}")
                    log.exception(e)
                    sleep(3)
                finally:
                    self.ib.lock_for_sync = False

            sleep(1)

            # Подписка на нужные события TWS
            self.maintain_subscriptions(force=True)

            # Отсечки времени для periodic_actions
            self.prev_maintain = monotonic()

            while not sleep(0.1) and self.ib.isConnected():
                try:
                    # Операции, которые нужно постоянно повторять
                    self.periodic_actions()

                except (KeyboardInterrupt, SystemExit) as e:
                    raise e

                except FatalException as e:
                    log.error(f"Fatal exception: {e}")
                    break

                except TimeoutError as e:
                    log.error(f"{e}")

                except Exception as e:
                    # Что-то пошло не так, но соединение активно.
                    log.error(f"Worker exception: {e}")
                    log.exception(e)


############################


class Command(BaseCommand):
    """
    Синхронизация состояния базы с IB через TWS или Gateway.
    """

    def add_arguments(self, parser):
        parser.add_argument("--config", type=str, dest="config", default=DEF_CONFIG)

    def handle(self, **kwargs):
        config = yaml.full_load(open(abspath(kwargs["config"])))

        sync = Sync(config)

        while True:
            try:
                sync.run()
            except (KeyboardInterrupt, SystemExit):
                print()
                sync.ib.disconnect()  # приведет к остановке msg_thread
                log.info(f"DONE")
                break
            except Exception as e:
                # Что-то пошло не так очень глобально.
                log.error(f"Sync run exception: {e}")
                log.exception(e)

        # Подождать завершения активных потоков
        dt = monotonic()
        while len(threading.enumerate()) > 1 and monotonic() - dt < 2:
            sleep(0.05)

        for thread in threading.enumerate():
            if thread.name != "MainThread":
                log.error(f"Thread alive: {thread}")
