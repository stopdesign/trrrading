import json
import threading
import time

import redis
import yaml
from datetime import datetime
from os.path import abspath, join, dirname
from django.conf import settings
from django.core.management.base import BaseCommand
from ibkr_web_api import IbApi
from ibkr_web_api.session_storage import RedisStorage

from main.models import Order, Instrument, Position, Account
from termcolor import cprint


class Command(BaseCommand):
    finished = None

    def add_arguments(self, parser):
        parser.add_argument('broker', type=str)

    def check_new(self, ib, account):
        """
        Найти новые ордеры, отправить их в IBKR.
        """
        if threading.active_count() > 15:
            return
        new_orders = Order.objects.filter(status="New")
        for order in new_orders:
            self.submit_order(ib, account, order)

    def check_ibkr(self, ib, account):
        """
        Загрузить список ордеров, позиций и баланс аккаунта.
        """
        ib.reset_session()
        ib.load_session()

        print()
        print(datetime.now().replace(microsecond=0))

        data = {"filters": []}
        url = "/portal.proxy/v1/portal/iserver/account/orders"
        res = ib.request(url, "GET", data=data, is_json=True)
        print("Orders", res.status_code)
        if res.status_code == 200:
            try:
                res_data = res.json()
                for order_data in res_data.get("orders"):
                    self.parse_order(account, order_data)
            except ValueError as e:
                print(res.text)
                print("parsing error", e)
        # print(json.dumps(res.json(), indent=2, default=str))

        ib.reset_session()
        ib.load_session()

        # ОТКРЫТЫЕ ПОЗИЦИИ АККАУНТА
        url = f"/portal.proxy/v1/portal/portfolio/{account.uid}/positions"
        res = ib.request(url, "GET", data={}, is_json=True)
        print("Positions", res.status_code)

        updated_positions = []
        if res.status_code == 200:
            try:
                res_data = res.json()
                for position_data in res_data:
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
        # print(json.dumps(res.json(), indent=2, default=str))

    def parse_position(self, account, position_data):
        conid = position_data['conid']
        try:
            instrument = Instrument.objects.get(conid=conid)
        except Instrument.DoesNotExist:
            cprint(f"unknown instrument {conid}")
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
                    instrument=instrument
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
        order.status = "InProgress"
        order.save()

        ib.reset_session()
        ib.load_session()

        print("\n\nSUBMIT_ORDER")

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
        data = {"orders": [order_data]}
        url = f"/portal.proxy/v1/portal/iserver/account/{account.uid}/orders"
        res = ib.request(url, "POST", data=data, is_json=True)
        print("CREATE Order HTTP status code:", res.status_code)
        try:
            res_json = res.json()
        except:
            print(res.text)
            return

        # print(json.dumps(res_json, indent=2, default=str))

        if "error" in res_json:
            cprint(f"ERROR: {res_json['error']}", "red")
            cprint(f"RAW ERROR: {res_json}", "white")
            return

        if messages := res_json[0].get("message"):
            cprint(f"WARNING: {messages}", "yellow")

        # TODO: проверить, не было ли ошибок

        # Если просят подтвердить
        if confirmation_id := res_json[0].get("id"):
            # Подтверждение ордера
            url = f"/portal.proxy/v1/portal/iserver/reply/{confirmation_id}"
            res = ib.request(url, "POST", data={"confirmed": True}, is_json=True)
            print("CONFIRM Order HTTP status code:", res.status_code)
            # print(res.text)
            res_json = res.json()
            # print(json.dumps(res_json, indent=2, default=str))

        if "error" in res_json:
            cprint(f"ERROR: {res_json['error']}", "red")
            cprint(f"RAW ERROR: {res_json}", "white")
            order.status = "Error"
            order.save()
            return

        if order_id := res_json[0].get("order_id"):
            order.order_id = order_id
            order.status = "Sent"
            order.save()

            # Досрочная проверка открытых позиций
            self.check_ibkr(ib, account)
        else:
            order.status = "Error"
            order.save()

    def handle(self, *args, **kwargs):

        conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))

        # Загрузка конфига
        config = yaml.full_load(open(broker_config_path))

        username = config["username"]
        password = config["password"]
        paper = config["paper"]
        secret = config["secret"]

        redis_client = redis.Redis(
            settings.TREDIS_HOST,
            settings.TREDIS_PORT,
            settings.TREDIS_DB,
            settings.TREDIS_PASSWORD
        )
        storage = RedisStorage(
            session_name=username,
            redis_client=redis_client,
            secret=secret
        )

        ib = IbApi(
            username,
            password,
            session_storage=storage,
            paper=paper,
            debug=False
        )

        account = Account.objects.get(
            uid=config["account"],
            username=config["username"],
        )

        prev_dt = datetime(1900, 1, 1)
        while not self.finished:
            dt = datetime.utcnow().replace(microsecond=0)
            # Каждую секунду что-то проверять
            if dt.second != prev_dt.second:
                self.check_new(ib, account)
                if dt.second % 15 == 0:
                    self.check_ibkr(ib, account)
            time.sleep(0.01)
            prev_dt = dt
