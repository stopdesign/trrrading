import json
from secrets import token_hex
from time import sleep

from django.core.management.base import BaseCommand
from ibkr_web_api import IbApi
from main.models import Order, Instrument, Position, Account
from termcolor import cprint


# username = "vysoch218"
username = "gr5g2ry0"
password = ""
paper = True

ib = IbApi(username, password, paper, debug=False)


class Command(BaseCommand):
    finished = None
    ib = None

    def submit_order(self):
        ib.reset_session()
        ib.load_session()

        print("\n\nSUBMIT_ORDER")

        order_id = token_hex(4)

        # To have the order active in all sessions including the Premarket,
        # Regular Trading Hours and the Aftermarket hours,
        # you must use a Limit or Stop Limit type order and add "outsideRTH".
        order_data = {
            "conid": 265598,
            "cOID": order_id,
            "secType": "265598:STK",
            "orderType": "MKT",
            # "price": 180,
            "side": "BUY",
            "tif": "GTC",
            "quantity": 1,
            "outsideRTH": False,
            "useAdaptive": False,
        }
        cprint(json.dumps(order_data, indent=2, default=str), "white")
        data = {"orders": [order_data]}
        url = "/portal.proxy/v1/portal/iserver/account/DU1492107/orders"
        res = ib.request(url, "POST", data=data, is_json=True)
        print("CREATE Order HTTP status code:", res.status_code)
        print(res.text)
        # res_json = res.json()
        print("\n\n-----\n\n")

        res_json = res.json()

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
            print(res.text)
            res_json = res.json()
            print(json.dumps(res_json, indent=2, default=str))

        if "error" in res_json:
            cprint(f"ERROR: {res_json['error']}", "red")
            cprint(f"RAW ERROR: {res_json}", "white")
            return

    def new_db_order(self):
        account = Account.objects.get(id=1)
        instrument = Instrument.objects.get(symbol="MES")

        # order = Order.market_order(account, instrument, Order.Side.buy, 6)
        # order.save()

        order = Order.limit_order(account, instrument, Order.Side.buy, 2, 4400, outside_rth=False)
        order.save()

    def handle(self, *args, **options):

        self.new_db_order()

