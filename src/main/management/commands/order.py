import json
import redis
from django.core.management.base import BaseCommand
from main.models.order import new_local_id


BOT_CHANNEL = "5_BOT_ACTIONS"


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        redis_client = redis.Redis()

        # trailing_amount = None
        # trailing_percent = None

        action = {
            "action": "create_order",
            "order": {
                "local_id": new_local_id(),
                "sid": "IDEALPRO_EUR.USD",
                "amount": 1000,
                "type": "MKT",
                # "limit_price": 18.05,
                # "stop_price": 18.10,
                "rth": True,
            }
        }
        a = redis_client.publish(BOT_CHANNEL, json.dumps(action, default=str))
        print(a)

