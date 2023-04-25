from decimal import Decimal
import logging
from typing import Callable

from termcolor import colored

from trader.data_types import Order, Position

from .base_exchange import BaseExchange

log = logging.getLogger("exchange")


class Exchange(BaseExchange):
    """
    Живая торговля.
    """

    def __init__(self, on_event: Callable, account_uid: str, redis_client):
        super().__init__(on_event)
        self.account["uid"] = account_uid

        # Это связь всей платформы с джангой
        from main.sync_client import SyncClient

        self.sync_client = SyncClient(
            self.positions,
            self.orders,
            self.account,
            redis_client,
        )

    def init_positions(self, sids):
        """
        Пустые позиции заполняются один раз,
        чтобы не было ошибок в процессе работы.
        """
        self.sync_client.update_broker_data(None)
        if not self.positions:
            raise ValueError("Can't init empty positions")
        for sid in sids:
            if sid in self.positions:
                continue
            log.warning(f"Add zero position: {sid}")
            zero = Position(sid, capital=Decimal(0), amount=Decimal(0))
            self.positions[sid] = zero

    def place_order(self, order: Order):
        log.info(colored(f"PLACE ORDER: {order}", "green"))
        self.sync_client.place_order(order)

    def update_order(self, order: Order, **kwargs):
        updated = False
        for key, value in kwargs.items():
            if getattr(order, key, None) != value:
                updated = True
        if updated:
            log.info(colored(f"UPDATE ORDER: {order} {kwargs}", "cyan"))
            self.sync_client.update_order(order, **kwargs)
        else:
            log.info(colored(f"UPDATE ORDER: {order} {kwargs}, NO CHANGES", "cyan"))

    def cancel_order(self, order: Order):
        log.info(colored(f"CANCEL ORDER: {order}", "red"))
        self.sync_client.cancel_order(order)

    def on_broker_update(self, payload):
        # log.info(f"Update broker data: {payload}")
        self.sync_client.update_broker_data(payload)

        # для каждого изменившегося ордера вызвать событие
        for order in self.orders:
            # FIXME: только при изменении ордера
            self.on_event("order", dt=self.dt_last, payload=order)

    def process_orders(self):
        pass
