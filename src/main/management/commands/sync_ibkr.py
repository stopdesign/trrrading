import json
import re
import threading
import time
from datetime import datetime
from decimal import Decimal
from os.path import abspath, dirname, join

import redis
import requests as requests
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from ibkr_web_api import IBThinClient, RedisStorage
from main.models import Account, Instrument, Order, Position
from termcolor import cprint

ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


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
            cprint(f"send_telegram error, {r.status_code}", "red")
    except Exception as e:
        cprint(f"send_telegram exception, {e}", "red")


class Command(BaseCommand):
    finished = None

    def add_arguments(self, parser):
        parser.add_argument("broker", type=str)

    def check_new(self, ib, account):
        """
        Найти новые ордеры, отправить их в IBKR.
        """
        if threading.active_count() > 15:
            return
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
        if res.status_code == 200:
            try:
                self.parse_account(account, res.json)
            except ValueError as e:
                print(res.text)
                print("parsing error", e)
        else:
            print(res.status_code)
            print(res.text)
            cprint(f"check_accounts ERROR", "red")

    def parse_account(self, account, res_data):
        net_value = res_data.get("netliquidation")["amount"]
        print(f"Net Value: {net_value}")
        account.net_value = Decimal(net_value)

        cash_value = res_data.get("totalcashvalue")["amount"]
        account.cash_value = Decimal(cash_value)

        ex_liq_com = res_data.get("excessliquidity-c")["amount"]
        account.ex_liq_com = Decimal(ex_liq_com)

        ex_liq_sec = res_data.get("excessliquidity-s")["amount"]
        account.ex_liq_sec = Decimal(ex_liq_sec)

        account.save()

    def check_ibkr(self, ib, account):
        """
        Загрузить список ордеров, позиций и баланс аккаунта.
        """
        res = ib.accounts.orders()
        print("Orders", res.status_code)
        if res.status_code == 200:
            try:
                for order_data in res.json.get("orders"):
                    self.parse_order(account, order_data)
            except ValueError as e:
                print(res.text)
                print("parsing error", e)

        # ОТКРЫТЫЕ ПОЗИЦИИ АККАУНТА
        res = ib.portfolio.positions_simple(account.uid)
        print("Positions", res.status_code)

        updated_positions = []
        if res.status_code == 200:
            try:
                for position_data in res.json:
                    position = self.parse_position(account, position_data)
                    if position:
                        updated_positions.append(position.id)
            except ValueError as e:
                print(res.text)
                print("parsing error", e)

            # Если данные пришли, то удалить все позиции, которых нет в данных.
            if updated_positions:
                not_updated_positions = Position.objects.filter(
                    account=account, amount__gt=0
                ).exclude(id__in=updated_positions)
                for position in not_updated_positions:
                    position.amount = 0
                    position.avg_price = None
                    position.unrealized_pnl = None
                    position.save()

    def parse_position(self, account, position_data):
        conid = position_data["conid"]
        desc = position_data["contractDesc"]
        try:
            instrument = Instrument.objects.get(conid=conid)
        except Instrument.DoesNotExist:
            cprint(f"Unknown instrument {conid}, {desc}", "yellow")
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
        # cprint(json.dumps(order_data, indent=2, default=str), "blue")

        # TODO: Если при отправке ордера произошла ошибка,
        # TODO: то мы не знаем его id, а знаем только order_ref.

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
            # Если ордер в базе вообще никак не найдет — создать.
            if not order:
                ticker = order_data.get("ticker")
                try:
                    instrument = Instrument.objects.get(symbol=ticker)
                except Instrument.DoesNotExist:
                    cprint(f"unknown instrument {ticker}")
                    return
                order = Order(
                    account=account,
                    order_id=order_id,
                    local_id=local_id,
                    instrument=instrument,
                )
            order.status = order_data.get("status")

            order.filled = order_data.get("filledQuantity", 0)
            order.amount = order_data.get("remainingQuantity", 0) + order.filled

            order_type = order_data.get("origOrderType")
            order_type = order_type.replace("MARKET", Order.Type.mkt)
            order_type = order_type.replace("LIMIT", Order.Type.lmt)
            order.type = order_type

            if order_type == Order.Type.lmt:
                order.limit_price = order_data.get("price")

            if side := order_data.get("side"):
                if side == Order.Side.buy.value:
                    order.action = Order.Side.buy
                if side == Order.Side.sell.value:
                    order.action = Order.Side.sell

            order.avg_fill_price = order_data.get("avgPrice")
            try:
                order.save()
            except Exception as e:
                cprint("ERROR: %s" % e, "red")

    def submit_order(self, ib, account, order):
        print("\nSUBMIT_ORDER")

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
            "useAdaptive": False,
        }
        if order.type == Order.Type.lmt:
            order_data["price"] = float(order.limit_price)

        cprint(json.dumps(order_data, indent=2, default=str), "white")

        res = ib.accounts.place_order(account.uid, order_data, confirm=True)

        if type(res.json) is list and "order_id" in res.json[0]:
            order.order_id = res.json[0]["order_id"]
            order.status = "Sent"
            order.save()

            # Досрочная проверка открытых позиций
            self.check_ibkr(ib, account)

            cprint(f"Order OK: {json.dumps(res.json, indent=2)}", "blue")

        else:
            order.status = "Error"
            order.save()

            cprint(f"Order ERROR: {res}", "red")

    def handle(self, **kwargs):

        conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))

        # Загрузка конфига
        config = yaml.full_load(open(broker_config_path))

        username = config["username"]
        secret = config["secret"]
        redis_config = config["redis"]
        uid = config["account"]

        redis_client = redis.Redis(**redis_config)
        rs = RedisStorage(username, redis_client, secret)

        ib = IBThinClient(username, storage=rs)
        ib.load_session()

        account = Account.objects.get(uid=uid, username=username)

        send_telegram(f"Start sync_ibkr for {username} {account.uid}")

        prev_dt = datetime(2000, 1, 1)
        while not self.finished:
            try:
                dt = datetime.utcnow().replace(microsecond=0)
                # Каждую секунду что-то проверять
                if dt.second != prev_dt.second:
                    self.check_new(ib, account)
                    if dt.second % 15 == 0:
                        ib.load_session()
                        self.check_ibkr(ib, account)
                        self.check_account(ib, account)
                time.sleep(0.1)
                prev_dt = dt
            except KeyboardInterrupt:
                break
        print("\nDone")
