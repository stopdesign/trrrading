import datetime as dt
from zoneinfo import ZoneInfo

from django.db import models


# FIXME: вынести в утилиты
def parseIBDatetime(s: str) -> dt.date | dt.datetime:
    """Parse string in IB date or datetime format to datetime."""
    if len(s) == 8:
        # YYYYmmdd
        y = int(s[0:4])
        m = int(s[4:6])
        d = int(s[6:8])
        t = dt.date(y, m, d)
    elif s.isdigit():
        t = dt.datetime.fromtimestamp(int(s), dt.timezone.utc)
    elif s.count(' ') >= 2 and '  ' not in s:
        # 20221125 10:00:00 Europe/Amsterdam
        s0, s1, s2 = s.split(' ', 2)
        t = dt.datetime.strptime(s0 + s1, '%Y%m%d%H:%M:%S')
        t = t.replace(tzinfo=ZoneInfo(s2))
    else:
        # YYYYmmdd  HH:MM:SS
        # or
        # YYYY-mm-dd HH:MM:SS.0
        ss = s.replace(' ', '').replace('-', '')[:16]
        t = dt.datetime.strptime(ss, '%Y%m%d%H:%M:%S')
    return t


class Trade(models.Model):
    # ExecId: 00012ec5.6417f067.01.01,
    # Time: 20230228  14:26:45,
    # Account: DU230020,
    # Exchange: ISLAND,
    # Side: SLD,
    # Shares: 50.000000,
    # Price: 90.100000,
    # PermId: 1080132998,   --- The TWS order identifier.
    # ClientId: 0,
    # OrderId: 0,
    # Liquidation: 0,
    # CumQty: 50.000000,
    # AvgPrice: 90.100000,
    # OrderRef: ,           --- реально OrderRef ордера присылают
    # EvRule: ,
    # EvMultiplier: 0.000000,
    # ModelCode: ,
    # LastLiquidity: 1

    account = models.ForeignKey("Account", null=True, on_delete=models.PROTECT)
    order = models.ForeignKey(
        "Order", null=False, on_delete=models.CASCADE, related_name="trades"
    )
    amount = models.PositiveIntegerField(default=0)
    price = models.DecimalField(default=0, max_digits=15, decimal_places=6)

    exec_id = models.CharField(max_length=50, unique=True, null=True)
    exchange = models.CharField(max_length=50)

    time = models.DateTimeField(null=True)
    commission = models.DecimalField(null=True, max_digits=15, decimal_places=6)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order}, {self.amount}, {self.price}"

    @classmethod
    def from_ib(cls, execution, commission, account, order):
        # filled = order.filledQuantity if order.filledQuantity < UNSET_DOUBLE else 0
        commission_value = commission.commission if commission else 0
        return cls(
            account=account,
            order=order,
            amount=execution.shares,
            price=execution.price,
            exec_id=execution.execId,
            exchange=execution.exchange,
            time=parseIBDatetime(execution.time),
            commission=commission_value,
        )

    @property
    def signed_amount(self):
        """
        TODO: save direction in Trade
        """
        if self.order.action == "BUY":
            return self.amount
        else:
            return -self.amount

    class Meta:
        app_label = "main"
