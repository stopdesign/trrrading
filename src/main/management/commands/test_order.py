import json
from os.path import abspath, dirname, join
from secrets import token_hex

import redis
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from ibkr_web_api import IBThinClient, RedisStorage
from main.models import Account, Instrument, Order, Position
from termcolor import cprint


class Command(BaseCommand):
    finished = None
    ib = None

    def add_arguments(self, parser):
        parser.add_argument("broker", type=str)

    def new_api_order(self, config):

        username = config["username"]
        secret = config["secret"]
        redis_config = config["redis"]
        account_uid = config["account"]

        redis_client = redis.Redis(**redis_config)
        rs = RedisStorage(username, redis_client, secret)

        ib = IBThinClient(username, storage=rs)

        #######################################################

        ib.load_session()

        print()
        print("SUBMIT_ORDER")

        order_id = token_hex(4)

        # To have the order active in all sessions including the Premarket,
        # Regular Trading Hours and the Aftermarket hours,
        # you must use a Limit or Stop Limit type order and add "outsideRTH".
        order_data = {
            "conid": 265598,
            "cOID": order_id,
            "secType": "265598:STK",  # Без этого тоже работает
            "orderType": "MKT",
            # "price": 180,
            "side": "BUY",
            "tif": "GTC",
            "quantity": 1,
            "outsideRTH": False,
            "useAdaptive": False,
        }
        cprint(json.dumps(order_data, indent=2, default=str), "white")
        
        res = ib.accounts.place_order(account_uid, order_data, confirm=True)
        
        if res.json:
            print(json.dumps(res.json, indent=2))
        else:
            print(res)

    def new_db_order(self):
        account = Account.objects.get(id=1)
        instrument = Instrument.objects.get(symbol="MES")

        order = Order.market_order(account, None, instrument, Order.Side.sell, 1)
        order.save()

        # order = Order.limit_order(account, instrument, Order.Side.buy, 2, 4400, outside_rth=False)
        # order.save()

    def handle(self, *args, **kwargs):

        conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))

        # Загрузка конфига
        config = yaml.full_load(open(broker_config_path))

        # self.new_api_order(config)

        self.new_db_order()
