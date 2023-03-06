import json
from os.path import abspath, dirname, join
from secrets import token_hex

import redis
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand
from main.models import Account, Order, Contract 
from termcolor import cprint
from django.core.cache import cache


class Command(BaseCommand):
    finished = None
    ib = None

    def new_api_order(self):

        account = Account.objects.get(id=2)

        print(account.uid)

    def new_db_order(self):
        account = Account.objects.get(id=4)
        instrument = Contract.objects.get(symbol="AAPL")

        # order = Order.market_order(account, None, instrument, Order.Side.sell, 1)

        price = 140
        order = Order.limit_order(account, instrument, Order.Side.buy, 1, price, outside_rth=False )
        order.save()
        
        print(order.local_id, price)

    def handle(self, *args, **kwargs):

        # conf_dir = join(dirname(settings.BASE_DIR), "bot_config")

        # broker_config_path = abspath(join(conf_dir, kwargs.get("broker")))

        # # Загрузка конфига
        # config = yaml.full_load(open(broker_config_path))

        # self.new_api_order()

        # self.new_db_order()

        # last_connected = cache.get("last_connected", "---")
        # print("last_connected", last_connected)

        # host: 137.220.48.251
        # port: 6379
        # db: 0
        # password: hFu1asd8331GjaIOm2Nds0

        redis_client = redis.Redis(host="137.220.48.251", password="hFu1asd8331GjaIOm2Nds0")
    
        action = {"action": "new_order", "data": "asdfs"}
        a = redis_client.publish("BOT_ACTIONS", json.dumps(action, default=str))
        print(a)

