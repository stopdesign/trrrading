import json
import logging
import socket
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from posixpath import abspath
from time import monotonic, sleep
from zoneinfo import ZoneInfo

import redis
import yaml
from django.core.management.base import BaseCommand
from django.db import transaction
from ib_sync import IBSync, IBThread
from ibapi.order import Order as IBOrder
from termcolor import colored

from main.models import Account, Contract, Order, Position, Trade
from project.helpers.alert import TgAlert

from .ib_orders import CustomIBOrder, StateNew  # FIXME: унести в ib_sync

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
BOT_CHANNEL = "BOT_ACTIONS"

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


def ibc_run_command(config, command):
    """
    Подключается в сокет канала управления IBC,
    отправляет команду, читает ответ.
    """
    status = ""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)

    try:
        sock.connect((config["host"], config["port"]))
        sock.sendall((f"{command}\n").encode())
        status = sock.recv(1024).decode("utf-8")
        sock.sendall(b"EXIT\n")
    except Exception as e:
        status = f"Error: {e}"
    finally:
        sock.close()

    return status


############################


class IBSyncExtended(IBSync):
    def __init__(self, tg_alert, redis_publish):
        super().__init__()
        self.tg = tg_alert
        self.redis_publish = redis_publish
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
        for r_id, sub in self.request.items():
            if not sub.get("cancelled"):
                self.request[r_id]["cancelled"] = True

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

        # Закэшированные начения из updateAccountValue
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
        """
        Эта штука пишет только PnL и цену позиций, не критично.
        """
        if self.lock_for_sync:
            return

        self.prev_time["updatePortfolio"] = monotonic()

        account = Account.objects.get(uid=accountName)

        # В данном случае контракт приходит достаточно наполненный.
        # Есть корректное значение primaryExchange для ARCA и дата
        # экспирации для фьючерсов. sid_for_contract должен сработать.

        sid = self.sid_for_contract(contract)

        log.debug(colored(f"updatePortfolio: {sid} {position}", "cyan"))

        try:
            db_position = Position.objects.get(account=account, contract__sid=sid)
            db_contract = db_position.contract
        except Position.DoesNotExist:
            log.error(f"Position not found: ib = {position}")
            return

        if db_position.amount != position:
            log.error(f"Position missmatch: db = {db_position.amount}, ib = {position}")

        avg_price = Decimal(averageCost) / db_contract.multiplier
        avg_price = round(avg_price / db_contract.min_tick) * db_contract.min_tick
        avg_price = avg_price * db_contract.price_magnifier

        db_position.avg_price = avg_price
        db_position.unrealized_pnl = unrealizedPNL
        db_position.save(update_fields=["avg_price", "unrealized_pnl"])

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
        super().orderStatus(
            orderId,
            status,
            filled,
            remaining,
            avgFillPrice,
            permId,
            parentId,
            lastFillPrice,
            clientId,
            whyHeld,
            mktCapPrice,
        )

        if self.lock_for_sync:
            return

        self.prev_time["orderStatus"] = monotonic()

        av_fill_price = avgFillPrice if avgFillPrice < 10**10 else None

        if permId and permId in self._orders_by_pid:
            # TODO: для активного ордера проверить время его получения
            order, contract, state = self._orders_by_pid[permId]
        else:
            log.error(f"Order not found in cache, {permId}")
            return

        sid = self.sid_for_contract(contract)

        log.info(
            colored(
                (
                    f"OrderStatus: oId: {orderId}, "
                    f"clientId: {clientId}, "
                    f"SID: {sid}, "
                    f"pId: {permId}, "
                    f"{state.status} >> {status}, "
                    f"amnt: {filled}/{remaining+filled}"
                    # f"lmt: {order.lmtPrice}, "
                    # f"aux: {order.auxPrice}, "
                    # f"fill: {av_fill_price}, "
                    # f"whyHeld: {whyHeld}"
                ),
                "blue",
            )
        )

        # TODO: закешировать?
        account = Account.objects.get(uid=order.account)

        with transaction.atomic():
            # Контракт достается из базы или создается
            try:
                db_contract = Contract.objects.get(sid=sid)
            except Contract.DoesNotExist:
                log.warn(f"Create new contract {sid}")
                cd = self.get_contract_details(contract)[0]
                db_contract = Contract.from_ib(contract, cd, sid)
                db_contract.save()

            try:
                # Два варианта:
                # - ордер создан на стороне IB, мы сразу знаем permId
                # - ордер создан через базу и лежит там без permId
                # Про ref нужно понимать, что чужие ref могут быть не уникальными.
                # Если в ref лежит наш идентификатор, то нужно сначала искать ордер
                # в базе по нему. Если не нашлось, то поискать по permId.

                log.debug(f"IBOrder: perm_id: {order.permId}, ref: {order.orderRef}")

                db_order = None

                if BOT_ID_PREFIX and BOT_ID_PREFIX in str(order.orderRef):
                    try:
                        db_order = Order.objects.get(
                            account=account,
                            local_id=order.orderRef,
                        )
                        db_order.order_id = order.permId  # сохранить себе permId
                    except Order.DoesNotExist:
                        log.warn(f"Bot order not found in DB: {order.orderRef}")

                # Ордер не из бота или не нашелся
                if not db_order:
                    db_order = Order.objects.get(order_id=order.permId)

                # FIXME: обновить обновляемые поля
                ib_order = Order.from_ib(order, account, db_contract, state)
                db_order.stop_price = ib_order.stop_price
                db_order.limit_price = ib_order.limit_price
                db_order.amount = ib_order.amount
                db_order.trailing_amount = ib_order.trailing_amount
                db_order.trailing_percent = ib_order.trailing_percent

            except Order.DoesNotExist:
                # Если ордера всё еще нет в базе - создать
                db_order = Order.from_ib(order, account, db_contract, state)

            log.debug(f"Order in DB {db_order}")

            # Используется последнее известное значение позиции контракта
            try:
                known_ib_position, avg_cost = self._positions_by_conid[contract.conId]
                avg_price = Decimal(avg_cost) / db_contract.multiplier
                avg_price = (
                    round(avg_price / db_contract.min_tick) * db_contract.min_tick
                )
                avg_price = avg_price * db_contract.price_magnifier
            except KeyError:
                known_ib_position, avg_cost = 0, None
                avg_price = None

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
                    db_position.avg_price = avg_price
                    db_position.amount = known_ib_position
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

            action = {
                "source": "order_status",
                "types": ["order", "position"],
                "info": {"sid": sid},
            }
            self.redis_publish(action)

            # После всего важного (блокирующий запрос)
            if pos_amount_changed:
                self.tg.message(f"Position {sid} {db_position.amount}")

    def updateAccountTime(self, *args, **kwargs):
        super().updateAccountTime(*args, **kwargs)
        self.prev_time["updateAccountTime"] = monotonic()
        log.debug(f"updateAccountTime: {args}")

    def updateAccountValue(self, key, value, currency, account):
        super().updateAccountValue(key, value, currency, account)
        self.prev_time["updateAccountValue"] = monotonic()
        if key == "NetLiquidation":
            txt = f"updateAccountValue: [{account}] {key} = {value} {currency}"
            log.info(colored(txt, "green"))

    #################################

    def process_bot_action(self, message):
        data = json.loads(message.get("data").decode())
        log.info(colored(f"From Redis: {data}", "white"))

        if data.get("action") == "create_order":
            self.create_order(data["order"])
            return

        if data.get("action") == "update_order":
            self.update_order(data["order"])
            return

        if data.get("action") == "cancel_order":
            self.cancel_order(data["order"])
            return

        log.error(f"Unknown bot action: {message}")

    def place_test_order(self) -> None:
        """
        Создается whatIf ордер, чтобы проверить openOrder callback.
        """
        oid = self.nextValidOrderId
        self.nextValidOrderId += 1

        contract = self.contract_for_sid("ARCA_SPY")

        # TODO: вынести в ib_orders

        order = IBOrder()
        order.orderId = oid
        order.action = "BUY"
        order.totalQuantity = Decimal(1)
        order.orderType = "LMT"
        order.lmtPrice = 100
        order.whatIf = True

        # Синхронная отправка ордера
        try:
            contract, order_res, orderState = self.place_order(contract, order)
            txt = f"WTF order: {order_res} | Status: {orderState.status}"
            log.info(colored(txt, "white"))
        except Exception as e:
            txt = f"Test order error: {order} {e}"
            log.error(txt)
            self.tg.message(txt)

    def create_order(self, data):
        """
        Создание ордера в IB
        """
        # ib_contract - нужен для отправки ордера в IB
        # db_contract - нужен для сохранения ордера в базе

        sid = data.get("sid")

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

        ib_order = CustomIBOrder(ib_contract, data)

        ib_order.orderId = self.nextValidOrderId
        self.nextValidOrderId += 1

        # Дерзкая конвертация ордера в модель

        db_order = Order.from_ib(ib_order, db_account, db_contract, StateNew())

        # Создать ордер в базе данных
        db_order.save()

        log.info(colored(f"Create, ib_order: {ib_order}", "green"))

        # Синхронная отправка ордера
        try:
            ib_order, _, state = self.place_order(ib_contract, ib_order)
            db_order.status = str(state.status)
            db_order.save()
            self.tg.message(f"Order created: {db_order}")
        except Exception as e:
            db_order.status = "Error"
            db_order.system_comment = f"{e}"
            db_order.save()
            txt = f"Create order error: {db_order} {e}"
            log.error(txt)
            self.tg.message(txt)

    def update_order(self, data):
        """
        Редактирование ордера в IB
        """
        local_id = data.get("local_id")

        inactive = ["Filled", "Cancelled", "ApiCancelled", "Inactive"]

        for ib_order, contract, orderState in self._orders_by_pid.values():
            if orderState.status in inactive:
                continue
            if ib_order.orderRef == local_id:
                sid = self.sid_for_contract(contract)
                if ib_order.orderId:
                    # собирается новый ib_order
                    updated_ib_order = CustomIBOrder(contract, data)
                    updated_ib_order.orderId = ib_order.orderId
                    log.info(colored(f"Update, ib_order: {ib_order}", "cyan"))
                    try:
                        self.place_order(contract, updated_ib_order)
                    except Exception as e:
                        txt = f"Update order: {sid} {updated_ib_order} {e}"
                        log.error(txt)
                        self.tg.message(txt)
                else:
                    txt = f"Can't update order: {ib_order}, {orderState.status}"
                    log.error(txt)
                    self.tg.message(txt)
                return

        log.error(f"Order not found: {data}")

    def cancel_order(self, data):
        """
        Отмена ордера в IB
        """
        local_id = data.get("local_id")
        order_id = data.get("order_id")  # для отмены ордеров другого клиента

        inactive = ["Filled", "Cancelled", "ApiCancelled", "Inactive"]

        # FIXME: _orders_by_pid обновляется в openOrder и не ловит состояние canceled
        for ib_order, contract, orderState in self._orders_by_pid.values():
            if orderState.status in inactive:
                continue
            if ib_order.orderRef == local_id or ib_order.permId == order_id:
                sid = self.sid_for_contract(contract)
                if ib_order.orderId:
                    self.cancelOrder(ib_order.orderId, "")
                    log.info(colored(f"Cancel order: {sid} {ib_order}", "magenta"))
                    self.tg.message(f"Cancel order: {sid} {ib_order}")
                else:
                    log.error(f"Can't cancel order: {ib_order}, {orderState.status}")
                return

        log.error(f"Order not found: {data}")


############################


class Sync:
    def __init__(self, config: dict) -> None:
        self.redis_config = config.get("redis", {})
        self.gateway_config = config.get("gateway", {})
        self.ibc_config = config.get("ibc", {})
        self.running = True

        # Разделение live и paper по разным каналам pubsub
        redis_db = self.redis_config.get("db", 0)
        self.sync_channel = f"{redis_db}_{SYNC_CHANNEL}"
        self.bot_channel = f"{redis_db}_{BOT_CHANNEL}"

        self.tg = TgAlert(config.get("telegram", {}))

        # Отметки, когда что произошло
        self.request_time = datetime.min
        self.prev_executions = monotonic()
        self.prev_subscribe = monotonic()
        self.prev_test_order = monotonic()

        self.gw_client_id = self.gateway_config.get("sync_client_id", 0)

        self.tg.message("Start Sync")

        log.info(colored("Start Sync ⋅ﾐ(•ᵕ•)ﾉ", "magenta"))
        log.info(f"Gateway: {self.gateway_config}")
        log.info(f"Redis: {self.redis_config}")

        self.rc = redis.Redis(**dict(self.redis_config))
        self.ib = IBSyncExtended(self.tg, self.redis_publish)

        self.pubsub = self.rc.pubsub()
        self.pubsub.subscribe(self.bot_channel)

        # FIXME:
        self.pnl_r_id = 0

        self.in_ibkr_long_break = False

    def request_tws_time(self) -> None:
        self.request_time = datetime.utcnow()
        self.ib.reqCurrentTime()

    def redis_publish(self, action: dict) -> None:
        json_str = json.dumps(action, default=str)
        a = self.rc.publish(self.sync_channel, json_str)
        log.info(f"To Redis: {json_str}, {a}")

    def is_delayed(self, event: str, max_delay: int, alert: bool = True) -> bool:
        """
        Проверка задержки данного типа события и алерт.
        """
        delay = monotonic() - self.ib.prev_time[event]
        if delay > max_delay:
            if alert:
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
            # self.ib.prev_time["openOrder"] = monotonic()

            if self.gw_client_id == 0:
                # С AutoBind новые ордеры из TWS получают id от данного клиента.
                # Работает только для подключения с ClientId = 0.
                self.ib.reqAutoOpenOrders(bAutoBind=True)
            else:
                log.warning(colored("Client ID != 0, no AutoBind", attrs=["bold"]))
                self.ib.reqOpenOrders()

        ########################################
        # Подписка на поля аккаунта и PnL
        # updateAccountValue
        # updateAccountTime
        # updatePortfolio

        # Переподписываться без алерта, если данных давно не было
        d_1 = force or self.is_delayed("updateAccountValue", 200, False)
        d_2 = force or self.is_delayed("updateAccountTime", 200, False)
        d_3 = force or self.is_delayed("updatePortfolio", 200, False)

        if d_1 or d_2 or d_3:
            self.ib.reqAccountUpdates(False, self.ib.account_id)  # Отписка
            sleep(0.01)
            self.ib.reqAccountUpdates(True, self.ib.account_id)  # Подписка
            sleep(0.01)

        # Алерты, если данных не было очень давно
        if not force:
            self.is_delayed("updateAccountValue", 220)
            self.is_delayed("updateAccountTime", 220)
            self.is_delayed("updatePortfolio", 220)
            self.is_delayed("pnl", 220)

        ########################################
        # Подписка на PnL

        # Переподписка без алерта
        if force or self.is_delayed("pnl", 200, False):
            if self.pnl_r_id:
                self.ib.cancelPnL(self.pnl_r_id)
                self.pnl_r_id = 0
                sleep(0.01)

            # На это нельзя подписываться много раз, заебет
            self.pnl_r_id = self.ib.r_id
            self.ib.reqPnL(self.pnl_r_id, self.ib.account_id, "")
            sleep(0.01)

    def get_executions(self) -> None:
        account = Account.objects.get(uid=self.ib.account_id)

        utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
        too_old = utc_now - timedelta(days=5)

        trades = Trade.objects.filter(account=account, created_at__gt=too_old)
        trades_by_exec_id = {t.exec_id: t for t in trades.order_by("-id")}

        orders = Order.objects.filter(account=account, created_at__gt=too_old)
        orders_by_id = {o.order_id: o for o in orders.order_by("-id")}

        executions = self.ib.get_executions()

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
                    # Resync orders (+ contracts)
                    ib_orders = self.ib.get_orders()
                    self.sync_orders(account, ib_orders)

        if trades_to_create:
            Trade.objects.bulk_create(trades_to_create)
            self.redis_publish({"source": "executions", "types": ["trade"]})

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
        contracts_to_create = []
        for contract in uniq_contracts.values():
            # self.ib.qualify_contract(contract)
            sid = self.ib.sid_for_contract(contract)
            if sid not in contracts_by_sid:
                cd = self.ib.get_contract_details(contract)[0]
                c = Contract.from_ib(contract, cd, sid)
                contracts_by_sid[sid] = c
                contracts_to_create.append(c)
                log.info(f"Create contract: {c.sid}")
        return contracts_to_create

    def sync_orders(self, account, ib_orders):
        """
        Создать в базе новые ордеры из IB, обновить старые.
        """
        # Все известные контракты из базы
        contracts = Contract.objects.all()
        contracts_by_sid = {c.sid: c for c in contracts}

        utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
        too_old = utc_now - timedelta(days=5)

        orders = Order.objects.filter(account=account, created_at__gt=too_old)
        orders_by_id = {o.order_id: o for o in orders.order_by("-id")}

        uniq_contracts = {r[0].conId: r[0] for r in ib_orders}
        if nc := self.get_new_contracts(contracts_by_sid, uniq_contracts):
            # Создаются неизвестные контракты
            Contract.objects.bulk_create(nc)

            # Перезагрузка контрактов
            contracts = Contract.objects.all()
            contracts_by_sid = {c.sid: c for c in contracts}

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

        # Перезагрузить все контракты из базы
        contracts = Contract.objects.all()
        contracts_by_sid = {c.sid: c for c in contracts}

        ############
        # Ордеры
        self.sync_orders(account, ib_orders)

        ############
        # Позиции

        positions_to_create = []

        # Всем обнуляю значения, но пока не сохраняю
        for position in positions_by_sid.values():
            position.amount = 0
            position.avg_price = None

        for acnt, contract, pos, avg_cost in ib_positions:
            sid = self.ib.sid_for_contract(contract)
            db_contract = contracts_by_sid[sid]

            if acnt != account.uid:
                log.warn(f"Skip wrong account: {acnt}")
                continue

            avg_price = Decimal(avg_cost) / db_contract.multiplier
            avg_price = round(avg_price / db_contract.min_tick) * db_contract.min_tick
            avg_price = avg_price * db_contract.price_magnifier

            if sid in positions_by_sid:
                # update position
                position = positions_by_sid[sid]
                position.avg_price = avg_price
                position.amount = pos
                if pos == 0:
                    position.unrealized_pnl = None
            else:
                # create position
                position = Position.from_ib(account, db_contract, pos, avg_price)
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
        if monotonic() - self.prev_subscribe > 17:
            self.prev_subscribe = monotonic()
            self.maintain_subscriptions()

    def long_break(self) -> bool:
        """
        Пятничный долгий перерыв IBKR.
        Часовой пояс Los Angeles, чтобы перерыв поместился в один день.
        Вообще он с 20, но после 17 всё равно ничего не работает.
        """
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        return now.isoweekday() == 5 and now.hour >= 18

    def run(self) -> None:
        """
        Бесконечный цикл, в котором поддерживаются нужные
        соединения с TWS/GW и нужные подписки на данные.
        """
        while not sleep(0.1) and self.running:
            # Во время большого перерыва ничего не делать
            if self.long_break():
                if not self.in_ibkr_long_break:
                    log.warning("Enter IBKR long break")
                    self.in_ibkr_long_break = True
                    self.ib.disconnect()
                continue
            elif self.in_ibkr_long_break:
                log.warning("Exit IBKR long break")
                self.in_ibkr_long_break = False

            # Попытка дисконнекта, если есть чего
            try:
                if self.ib:
                    self.ib.disconnect()
            except Exception as e:
                log.error(f"TWS disconnect exception: {e}")

            # Подключение к TWS
            try:
                host = self.gateway_config["host"]
                port = self.gateway_config["port"]
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
            while not sleep(0.1) and not self.long_break():
                self.ib.lock_for_sync = True

                try:
                    with transaction.atomic():
                        self.initial_sync()
                        # Уведомление после успешной синхронизации
                        self.redis_publish({"source": "sync", "types": ["all"]})
                        break

                except Exception as e:
                    log.error(f"Initial sync error: {e}, reconnect")
                    log.exception(e)
                    res = ibc_run_command(self.ibc_config, "RECONNECTACCOUNT")
                    log.info(f"IBC reconnect account: {res}")
                    sleep(5)

                finally:
                    self.ib.lock_for_sync = False

            sleep(1)

            # Подписка на нужные события TWS
            self.maintain_subscriptions(force=True)

            # Отсечки времени для periodic_actions
            self.prev_maintain = monotonic()

            while not sleep(0.1) and not self.long_break():
                try:
                    # Операции, которые нужно постоянно повторять
                    self.periodic_actions()

                except (KeyboardInterrupt, SystemExit) as e:
                    raise e

                except FatalException as e:
                    txt = f"Fatal exception: {e}"
                    log.error(txt)
                    self.tg.message(txt)
                    break

                except TimeoutError as e:
                    txt = f"{e}"
                    log.error(txt)
                    self.tg.message(txt)

                except Exception as e:
                    # Что-то пошло не так, но соединение активно.
                    txt = f"Worker exception: {e}"
                    log.error(txt)
                    log.exception(e)
                    self.tg.message(txt)


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
                txt = f"Sync run exception: {e}"
                log.error(txt)
                log.exception(e)
                sync.tg.message(txt)

        # Подождать завершения активных потоков
        dt = monotonic()
        while len(threading.enumerate()) > 1 and monotonic() - dt < 2:
            sleep(0.05)

        for thread in threading.enumerate():
            if thread.name != "MainThread":
                log.error(f"Thread alive: {thread}")
