import logging
from typing import Callable
from termcolor import colored
from trader2 import BaseExchange, SyncClient

log = logging.getLogger("exchange")


class Exchange(BaseExchange):
    """
    Живая торговля.
    """

    def __init__(self, on_event: Callable, account_uid: str):
        super().__init__(on_event)
        self.account["uid"] = account_uid
        self.sync_client = SyncClient(self.positions, self.orders, self.account)

    def place_order(self, order):
        log.info(colored(f"PLACE ORDER: {order}", "magenta"))
        self.sync_client.place_order(order)

    def on_broker_update(self, payload):
        log.info(f"Update broker data: {payload}")
        self.sync_client.update_broker_data()

        # для каждого изменившегося ордера вызвать дернуть событие
        for order in self.orders:
            # TODO: только при изменении ордера
            self.on_event("order", dt=self.dt_last, payload=order)
