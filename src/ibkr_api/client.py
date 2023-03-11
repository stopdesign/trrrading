from datetime import datetime, timedelta
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import TickerId
from ibapi.execution import ExecutionFilter
import threading
import time
from termcolor import colored, cprint
import logging
import sys
import random


# Логгер для этого файла
log = logging.getLogger("ib_api.client")
log.setLevel(logging.INFO)



class IBClient(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.order_status = {}
        self.nextValidOrderId = None
        self.account_id = None
        self.values = {}

    def connectAck(self):
        super().connectAck()
        log.warn("Connected")

        # Подписаться на всё необходимое

    def connectionClosed(self):
        super().connectionClosed()
        log.warn("connectionClosed")

    def nextValidId(self, orderId):
        print("Next Valid Id", orderId)
        self.nextValidOrderId = orderId

    def managedAccounts(self, accountsList:str):
        """Receives a comma-separated string with the managed account ids."""
        super().managedAccounts(accountsList)
        self.account_id = accountsList.split(",")[0]
        self.values[self.account_id] = {}
        log.info(f"Managed account: {self.account_id}")

    # def openOrder(self, orderId, contract, order, orderState):
    #     super().openOrder(orderId, contract, order, orderState)
    #     print(f'Order opened: {orderId}, order: "{order}", status: {orderState.status}')

    # def completedOrder(self, contract, order, orderState):
    #     super().completedOrder(contract, order, orderState)
    #     print(f'Completed order: "{order}", status: {orderState.status}')

    # def completedOrdersEnd(self):
    #     super().completedOrdersEnd()
    #     print('//// Completed Orders\n')

    # def openOrderEnd(self):
    #     super().openOrderEnd()
    #     print('//// Open Orders\n')

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        print(f'Order status updated for order ID {orderId}: status={status}, filled={filled}, remaining={remaining}, permId={permId}')

    # def execDetails(self, reqId, contract, execution):
    #     super().execDetails(reqId, contract, execution)
    #     print(f'EXECUTION for order ID: {execution.permId}', execution)

    # def execDetailsEnd(self, reqId):
    #     super().execDetailsEnd(reqId)
    #     print('//// Executions\n')

    # def position(self, account, contract, position, avgCost):
    #     super().position(account, contract, position, avgCost)
    #     print('Position: account={}, contract={}, position={}, avgCost={}'.format(account, contract.symbol, position, avgCost))
    
    # def positionEnd(self):
    #     super().positionEnd()
    #     print('//// Positions\n')

    def updateAccountValue(self, key, value, currency, accountName):
        self.values[accountName][key] = value
        # cprint('Account value updated: key={}, value={}, currency={}, accountName={}'.format(key, value, currency, accountName), "blue")

    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):
        cprint('Portfolio updated: contract={}, position={}, marketPrice={}, marketValue={}, averageCost={}, unrealizedPNL={}, realizedPNL={}, accountName={}'.format(contract.conId, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName), "red")

    def updateAccountTime(self, timestamp: str):
        pass
        # super().updateAccountTime(timestamp)
        # cprint(f"AccountTime: {timestamp}", "yellow")

    def orderBound(self, orderId: int, apiClientId: int, apiOrderId: int):
        super().orderBound(orderId, apiClientId, apiOrderId)
        cprint(f"OrderBound. OrderId: {orderId}, ApiClientId: {apiClientId}, ApiOrderId: {apiOrderId}", "blue")

    def currentTime(self, time):
        dt = datetime.utcfromtimestamp(time)
        # .strftime('%Y-%m-%d %H:%M:%S')
        print(f'Current TWS time: {dt} UTC')

    def pnl(self, reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float):
        cprint(f"Account dailyPnL: {dailyPnL}, unrealizedPnL: {unrealizedPnL}, realizedPnL: {realizedPnL}", "cyan")

    def accountSummary(self, reqId, account, tag, value, currency):
        super().accountSummary(reqId, account, tag, value, currency)
        dictionary = {"ReqId":reqId, "Account": account, "Tag": tag, "Value": value, "Currency": currency}
        cprint(f"Account Summary: {dictionary}", "magenta")

    def accountSummaryEnd(self, reqId: int):
        super().accountSummaryEnd(reqId)
        print('//// accountSummary\n')
    
    def error(self, reqId:TickerId, errorCode:int, errorString:str, advancedOrderRejectJson = ""):
        cprint(f"ERROR {errorCode} {errorString}", "red")

    def historicalData(self, reqId:int, bar):
        cprint(f"HistoricalData. BarData: {bar}", "blue")

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        super().historicalDataEnd(reqId, start, end)
        cprint(f"HistoricalDataEnd. ReqId: {reqId} from {start} to {end}", "red")

    def historicalDataUpdate(self, reqId: int, bar):
        cprint(f"HistoricalDataUpdate. BarData: {bar}", "magenta")

    def commissionReport(self, commissionReport):
        # super().commissionReport(commissionReport)
        pass

    def initialize(self):

        # self.reqPositions()

        # # раз в три минуты будет приходить summary
        # self.reqAccountSummary(1, "All", "NetLiquidation")

        # # Приходит real-time, поэтому удобно для тестов.
        # self.reqPnL(2, self.account_id, "")

        # # # Request open orders from all clients
        # self.reqAllOpenOrders()

        # # Requests status updates about future orders placed from TWS. 
        # # Can only be used with client ID 0.
        # if self.clientId == 0:
        #     self.reqAutoOpenOrders(True) 

        # self.reqCompletedOrders(apiOnly=False)

        self.reqIds(-1)

        # contract = StockContract("AAPL")
        # contract = FutContract("CL", "CLJ3", exchange="NYMEX")
        # contract = CryptoContract("ETH")
        # self.reqRealTimeBars(1010, contract, 5, "MIDPOINT", True, [])

        # Идея такая:
        #
        # Нужно сделать две группы запросов с интервалом N секунд.
        # Если результаты одинаковые, значит ситуация стабильна,
        # и можно сохранять данные как начальные.
        # Если результаты разные, то можно продолжать, 
        # пока две последовательные группы не совпадут.

        # Дальше это состояние сравнивается с базой.
        # Различия вываливаются в логи.
        
        # Дальше состояние в базе подгоняется к реальному.

        # Вроде как, надо бы попытаться позиции базы при помощи
        # новых исполненных ордеров. Но это сложно.
        # Лучше просто скопировать стабильное состояние в базу.
        # База долгосрочно может быть неконсистентна, но при непрерывной
        # работе синхронизации всё будет ok.



class IBThread(threading.Thread):
    def __init__(self, app):
        self.app = app
        super().__init__(target=self.run, daemon=True)

    def run(self):
        log.info("Run Message Thread")
        self.app.run()


def FxContract(symbol, secType="CASH", exchange="IDEALPRO", currency="USD"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = secType
    contract.exchange = exchange
    contract.currency = currency
    return contract


def FutContract(symbol, localSymbol, secType="FUT", exchange="CME", currency="USD"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = secType
    contract.exchange = exchange
    contract.currency = currency
    contract.localSymbol = localSymbol
    return contract


def CryptoContract(symbol, secType="CRYPTO", exchange="PAXOS", currency="USD"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = secType
    contract.exchange = exchange
    contract.currency = currency
    return contract


def StockContract(symbol, secType="STK", exchange="SMART", currency="USD"):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = secType
    contract.exchange = exchange
    contract.currency = currency
    return contract
