import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from os.path import abspath, dirname, join

import redis
import requests as requests
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from ibkr_web_api import IBThinClient, RedisStorage
from main.models import Account, Instrument, Order, Position

log = logging.getLogger("sync_ibkr")


ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


DEF_CONFIG = "../config/bot.yaml"


def send_telegram(text: str):
    """
    send_telegram("message text")
    """

    token = settings.TELEGRAM_TOKEN

    if not token:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "text": ansi_escape.sub("", text),
        "chat_id": settings.TELEGRAM_CHANNEL_ID,
        "parse_mode": "html",
    }
    try:
        r = requests.post(url, data=data, timeout=3)
        if r.status_code != 200:
            log.error(f"send_telegram error, {r.status_code}")
    except Exception as e:
        log.error(f"send_telegram exception, {e}")


def fractions_to_float(frac_str):
    if frac_str is None:
        return frac_str
    try:
        return float(frac_str)
    except ValueError:
        num, denom = frac_str.split('/')
        try:
            leading, num = num.split(' ')
            whole = float(leading)
        except ValueError:
            whole = 0
        frac = float(num) / float(denom)
        return whole - frac if whole < 0 else whole + frac


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--config", type=str, dest="config", default=DEF_CONFIG)

    def check_new(self, ib, account):
        """
        Найти новые ордеры, отправить их в IBKR.
        """
        new_orders = Order.objects.filter(status="New")
        for order in new_orders:
            order.status = "InProgress"
            order.save()
            self.submit_order(ib, account, order)

    def check_account(self, ib, account):
        """
        Загрузить список ордеров, позиций и баланс аккаунта.
        """
        res = ib.portfolio.summary(account.uid)
        if res.status_code != 200:
            log.error(f"Portfolio summary error: {res}")
            return
        try:
            self.parse_account(account, res.json)
        except (ValueError, TypeError, KeyError) as e:
            log.warning(res.text)
            log.error(f"Parsing error: {e}")

    def parse_account(self, account, res_data):
        net_value = res_data.get("netliquidation")["amount"]
        log.info(f"Net Value: {net_value}")
        account.net_value = Decimal(net_value)

        cash_value = res_data.get("totalcashvalue")["amount"]
        account.cash_value = Decimal(cash_value)

        ex_liq_com = res_data.get("excessliquidity-c")["amount"]
        account.ex_liq_com = Decimal(ex_liq_com)

        ex_liq_sec = res_data.get("excessliquidity-s")["amount"]
        account.ex_liq_sec = Decimal(ex_liq_sec)

        account.save()

    def check_orders(self, ib, account):
        """
        Загрузить список ордеров аккаунта.
        """
        res = ib.accounts.orders()

        if res.status_code != 200:
            log.error(f"Orders error: {res}")
            return

        # Проверить, что все недавние ордеры c order_id, есть в списке.
        # Был случай, когда filled-ордер отсутствовал,
        # но был виден по прямому запросу по orderId.
        # Всё сложно... Filled могут отсутствовать после перерыва сессии.
        min_dt = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(hours=1)
        to_be = Order.objects.filter(created_at__gt=min_dt, order_id__isnull=False)
        to_be = to_be.exclude(status__in=["Filled"])
        to_be = list(to_be.values_list("order_id", flat=True))

        try:
            for order_data in res.json.get("orders"):
                self.parse_order(account, order_data)
                if order_id := order_data.get("orderId"):
                    if order_id in to_be:
                        to_be.remove(order_id)
        except ValueError as e:
            log.warning(res.text)
            log.error(f"Parsing error: {e}")

        if to_be:
            log.error(f"Some new orders are not in the list: {to_be}")

    def check_positions(self, ib, account):
        """
        Загрузить список открытых позиций аккаунта.
        """
        res = ib.portfolio.positions_2(account.uid)

        if res.status_code != 200:
            log.error(f"Positions error: {res}")
            return

        updated_positions = []
        try:
            for position_data in res.json:
                position = self.parse_position(account, position_data)
                if position:
                    updated_positions.append(position.id)
        except ValueError as e:
            log.warning(res.text)
            log.error(f"Parsing error: {e}")

        # Если данные пришли, то удалить все позиции, которых нет в данных.
        if updated_positions:
            positions = Position.objects.filter(account=account, amount__gt=0)
            not_updated_positions = positions.exclude(id__in=updated_positions)
            for position in not_updated_positions:
                position.amount = 0
                position.avg_price = None
                position.unrealized_pnl = None
                position.save()

    def parse_position(self, account, position_data):
        conid = position_data["conid"]
        desc = position_data["description"]
        try:
            instrument = Instrument.objects.get(conid=conid)
        except Instrument.DoesNotExist:
            if conid not in self.unknown_instruments_cache:
                log.info(f"Unknown instrument {conid}, {desc}")
                self.unknown_instruments_cache.append(conid)
            return
        try:
            position = Position.objects.get(account=account, instrument=instrument)
        except Position.DoesNotExist:
            position = Position(account=account, instrument=instrument)
        position.amount = position_data.get("position", 0)
        position.avg_price = position_data.get("avgPrice") or None
        position.unrealized_pnl = position_data.get("unrealizedPnl") or None
        position.save()
        return position

    def parse_order(self, account, order_data):

        # если ордер создался штатно, то у него есть orderId
        if order_id := order_data.get("orderId"):
            order = None
            local_id = order_data.get("order_ref")
            try:
                order = Order.objects.get(order_id=order_id)
            except Order.DoesNotExist:
                if local_id:
                    try:
                        order = Order.objects.get(local_id=local_id)
                    except Order.DoesNotExist:
                        pass

            # Если ордер в базе вообще никак не найден — создать.
            if not order:
                ticker = order_data.get("ticker")
                try:
                    instrument = Instrument.objects.get(symbol=ticker)
                except Instrument.DoesNotExist:
                    log.warning(f"Unknown instrument {ticker} in new order")
                    return

                # Попытка распарсить время ордера.
                # Настоящее время создания нам не говорят.
                try:
                    order_ts = int(order_data.get("lastExecutionTime_r"))
                    order_dt = datetime.utcfromtimestamp(order_ts / 1000)
                    order_dt = order_dt.replace(tzinfo=timezone.utc)
                except:
                    order_dt = None

                order = Order(
                    account=account,
                    order_id=order_id,
                    local_id=local_id,
                    instrument=instrument,
                    created_at=order_dt,
                )

            order.system_comment = order_data.get("order_cancellation_by_system_reason")
            order.string_repr = order_data.get("orderDesc")
            order.status = order_data.get("status")

            order.filled = order_data.get("filledQuantity", 0)
            order.amount = order_data.get("remainingQuantity", 0) + order.filled

            order_type = order_data.get("origOrderType")
            order_type = order_type.replace("MARKET", Order.Type.mkt)
            order_type = order_type.replace("LIMIT", Order.Type.lmt)
            order.type = order_type

            if order_type == Order.Type.lmt:
                order.limit_price = fractions_to_float(order_data.get("price"))

            if side := order_data.get("side"):
                if side == Order.Side.buy.value:
                    order.action = Order.Side.buy
                if side == Order.Side.sell.value:
                    order.action = Order.Side.sell

            order.avg_fill_price = fractions_to_float(order_data.get("avgPrice"))
            try:
                order.save()
            except Exception as e:
                log.error(f"ERROR: {e}")

    def submit_order(self, ib, account, order):
        log.info("SUBMIT ORDER")

        # TODO: убрать блокирующую операцию до отправки ордера
        send_telegram(f"Order {account.uid} {order}")

        order_data = {
            "conid": order.instrument.conid,
            "cOID": order.local_id,
            "secType": f"{order.instrument.conid}:{order.instrument.sec_type}",
            "orderType": order.type,
            "side": order.action,
            "tif": "GTC",
            "quantity": order.amount,
            "outsideRTH": order.outside_rth,
            # "useAdaptive": False,  # не работает
        }
        if order.type == Order.Type.lmt:
            order_data["price"] = float(order.limit_price)

        # Проброс Adaptive
        if order.order_settings:
            try:
                conf = json.loads(order.order_settings)
                if conf.get("strategy") == "Adaptive":
                    order_data["tif"] = "DAY"
                    order_data["strategy"] = "Adaptive"
                    order_data["strategyParameters"] = {
                        "adaptivePriority": conf.get("priority", "Normal")
                    }
            except Exception as e:
                log.error(f"Bad order_settings: {order.order_settings}, {e}")

        log.info(json.dumps(order_data, indent=2, default=str))

        res = ib.accounts.place_order(account.uid, order_data, confirm=True)

        if type(res.json) is list and "order_id" in res.json[0]:
            order.order_id = res.json[0]["order_id"]
            order.status = "Sent"
            order.save()

            log.info(f"Order OK: {json.dumps(res.json, indent=2)}")

            # Досрочная проверка ордеров и позиций
            self.check_orders(ib, account)
            self.check_positions(ib, account)

        else:
            order.status = "Error"
            order.save()

            log.error(f"Order ERROR: {res}")

    def handle(self, **kwargs):

        self.unknown_instruments_cache = []

        conf_dir = join(dirname(settings.BASE_DIR))
        config_path = abspath(join(conf_dir, kwargs.get("config")))
        config = yaml.full_load(open(config_path))

        username = config["live"]["username"]
        secret = config["live"]["secret"]
        uid = config["live"]["account"]

        session_source = config["live"]["session"]
        redis_config = config["sources"][session_source]

        redis_client = redis.Redis(**redis_config)
        rs = RedisStorage(username, redis_client, secret)

        ib = IBThinClient(username, storage=rs)
        ib.load_session()

        account = Account.objects.get(uid=uid, username=username)

        send_telegram(f"Start sync_ibkr for {username} {account.uid}")

        prev_dt = datetime(2000, 1, 1)
        while dt := datetime.utcnow().replace(microsecond=0):
            try:
                if dt.second == prev_dt.second:
                    time.sleep(0.2)
                    continue
                prev_dt = dt
                self.check_new(ib, account)

                # Сервер лежит, не делать запросы
                if ib.ibkr_long_break():
                    log.info("IBKR long break")
                    continue

                # Сервер иногда полеживает, сократить частоту запросов
                if ib.ibkr_short_break():
                    if dt.minute % 10 != 0 and dt.second != 0:
                        log.info("IBKR short break")
                        continue
                
                if dt.second % 15 == 0:
                    ib.load_session()
                    self.check_orders(ib, account)
                    self.check_positions(ib, account)
                    self.check_account(ib, account)
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.exception(e)

        log.info("Done")
