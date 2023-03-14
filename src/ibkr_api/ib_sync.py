from datetime import datetime, timedelta
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract, ContractDetails

# from ibapi.order import *
from ibapi.execution import ExecutionFilter
import threading
import time
from termcolor import colored, cprint
import logging
import sys
import random
from timeout_decorator import timeout
from .client import IBClient


# Логгер для этого файла
log = logging.getLogger("ib_api.ib_sync")
log.setLevel(logging.INFO)


TIMEOUT = 5


class Results(list):
    def __init__(self):
        self.finished = False

    def finish(self, request_id=None):
        self.finished = True


class IBSync(IBClient):
    """
    Positions
    Executions (execDetails + commissionReport)
    Open + Completed Orders
    """

    def __init__(self):
        super().__init__()
        self._open_orders = Results()
        self._completed_orders = Results()
        self._positions = Results()
        self._executions = Results()
        self._contract_details = Results()

        # TODO: приделать протухание
        self._orders_by_pid = {}
        self._positions_by_conid = {}

    @property
    def r_id(self):
        return random.randint(10000000, 99999999)

    ##########################
    ### Positions

    @timeout(TIMEOUT)
    def get_positions(self) -> list[tuple]:
        self._positions_by_conid = {}
        self._positions = Results()
        self.reqPositions()

        while not self._positions.finished:
            time.sleep(0.001)

        return list(self._positions)

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        super().position(account, contract, position, avgCost)
        if account == self.account_id:
            self._positions_by_conid[contract.conId] = (position, avgCost)
        if not self._positions.finished:
            self._positions.append((account, contract, position, avgCost))

    def positionEnd(self):
        super().positionEnd()
        self._positions.finish()

    ##########################
    ### Orders

    @timeout(TIMEOUT)
    def get_orders(self):
        self._open_orders = Results()
        self._completed_orders = Results()

        self.reqAllOpenOrders()  # not a subscription
        self.reqCompletedOrders(apiOnly=False)  # not a subscription

        while not (self._open_orders.finished and self._completed_orders.finished):
            time.sleep(0.001)

        return list(self._open_orders + self._completed_orders)

    def openOrder(self, orderId, contract, order, orderState):
        # super().openOrder(orderId, contract, order, orderState)
        if not self._open_orders.finished:
            self._open_orders.append((contract, order, orderState))
        if order.permId:
            self._orders_by_pid[order.permId] = order, contract, orderState
        else:
            log.error(f"OpenOrder without permId: {order}")

    def completedOrder(self, contract, order, orderState):
        # super().completedOrder(contract, order, orderState)
        if not self._completed_orders.finished:
            self._completed_orders.append((contract, order, orderState))
        if order.permId:
            self._orders_by_pid[order.permId] = order, contract, orderState
        else:
            log.error(f"CompletedOrder without permId: {order}")

    def openOrderEnd(self):
        super().openOrderEnd()
        self._open_orders.finish()

    def completedOrdersEnd(self):
        super().completedOrdersEnd()
        self._completed_orders.finish()

    ##########################
    ### Executions

    @timeout(TIMEOUT)
    def get_executions(self):
        self._executions = Results()
        self.reqExecutions(self.r_id, ExecutionFilter())

        while not self._executions.finished:
            time.sleep(0.001)

        return list(self._executions)

    def execDetails(self, reqId, contract, execution):
        # super().execDetails(reqId, contract, execution)
        if not self._executions.finished:
            self._executions.append((contract, execution))

    def execDetailsEnd(self, reqId):
        # super().execDetailsEnd(reqId)
        self._executions.finish(reqId)

    ##########################
    ### Contracts

    @timeout(TIMEOUT)
    def get_contract_details(self, contract: Contract):
        self._contract_details = Results()
        self.reqContractDetails(self.r_id, contract)
        while not self._contract_details.finished:
            time.sleep(0.001)
        return list(self._contract_details)[0]

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        super().contractDetails(reqId, contractDetails)
        if not self._contract_details.finished:
            self._contract_details.append(contractDetails)

    def contractDetailsEnd(self, reqId: int):
        super().contractDetailsEnd(reqId)
        self._contract_details.finish()

    @timeout(TIMEOUT)
    def get_account_summary(self):
        pass
