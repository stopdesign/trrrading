import logging
from decimal import Decimal

from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.tag_value import TagValue

log = logging.getLogger("ib_orders")


class StateNew(OrderState):
    def __init__(self):
        self.status = "New"


def action_and_amount(data: dict) -> tuple[str, Decimal]:
    _amount = Decimal(data.get("amount", 0))
    if not _amount or _amount == 0:
        raise ValueError(f"Bad order amount: {str(data)}")
    action = "BUY" if _amount > 0 else "SELL"
    amount = abs(_amount)
    return action, amount


class WhatIfOrder(Order):
    def __init__(self) -> None:
        super().__init__()
        self.action = "BUY"
        self.totalQuantity = Decimal(1)
        self.orderType = "LMT"
        self.lmtPrice = 100
        self.whatIf = True


class CustomIBOrder(Order):
    """
    Штука создает IB Order по заданной конфигурации.
    """

    def __init__(self, contract: Contract, data: dict) -> None:
        super().__init__()

        # log.info(data)

        self.permId = None
        self.contract = contract

        action, amount = action_and_amount(data)

        self.orderRef = data.get("local_id")
        self.action = action
        self.totalQuantity = amount

        order_type = data.get("type")

        # TODO: "TRAIL", "TRAIL LIMIT"

        # MIDPRICE: DAY|GTC, RTH=True, lmtPrice (опциональнo), STK

        # ib_algo: тип MKT и LMT, tif=Day, RTH=True

        self.tif = "DAY"

        if order_type == "MKT":
            self._marker_order(data)
        elif order_type == "LMT":
            self._limit_order(data)
        elif order_type == "STP":
            self._stop_order(data)
        elif order_type == "STP LMT":
            self._stop_limit_order(data)
        elif order_type == "MIDPOINT":
            self._midpoint_order(data)
        else:
            raise ValueError(f"Unknown order type: {str(data)}")

    def _midpoint_order(self, data):
        self.orderType = "MIDPOINT"
        self.outsideRth = False
        if lmt := data.get("limit_price"):
            self.lmtPrice = float(lmt)

    def _ib_algo(self, data):
        ib_algo = data.get("ib_algo", {})
        if not ib_algo:
            return

        strategy = str(ib_algo.get("strategy", ""))
        params = [TagValue(*p) for p in ib_algo.get("params", {}).items()]

        if strategy not in ["Adaptive", "Twap", "ArrivalPx"]:
            raise ValueError(f"Unknown ib_algo_strategy: {strategy}, {str(data)}")

        self.algoStrategy = strategy
        self.algoParams = params  # type: ignore

    def _marker_order(self, data):
        self.orderType = "MKT"
        self.outsideRth = False
        self._ib_algo(data)

    def _limit_order(self, data):
        self.orderType = "LMT"
        self.outsideRth = not bool(data.get("rth", True))
        self._ib_algo(data)

        self.lmtPrice = float(data.get("limit_price"))

    def _stop_order(self, data):
        self.orderType = "STP"
        self.outsideRth = not bool(data.get("rth", True))

        self.auxPrice = float(data.get("stop_price"))
        self.trailStopPrice = self.auxPrice

    def _stop_limit_order(self, data):
        self.orderType = "STP LMT"
        self.outsideRth = not bool(data.get("rth", True))

        self.auxPrice = float(data.get("stop_price"))
        self.trailStopPrice = self.auxPrice

        self.lmtPrice = float(data.get("limit_price"))
