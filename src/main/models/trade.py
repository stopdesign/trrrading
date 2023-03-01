from django.db import models


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
    # AvgPrice: 90.100000,  --- что за нахуй?
    # OrderRef: ,           --- реально OrderRef ордера присылают
    # EvRule: , 
    # EvMultiplier: 0.000000, 
    # ModelCode: , 
    # LastLiquidity: 1

    account = models.ForeignKey("Account", null=True, on_delete=models.PROTECT)
    order = models.ForeignKey("Order", null=False, on_delete=models.CASCADE, related_name="trades")
    amount = models.PositiveIntegerField(default=0)
    price = models.DecimalField(default=0, max_digits=10, decimal_places=2)

    exec_id = models.CharField(max_length=50, unique=True, null=True)
    exchange = models.CharField(max_length=50)

    time = models.DateTimeField(null=True)
    commission = models.DecimalField(null=True, max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order}, {self.amount}, {self.price}"

    @classmethod
    def from_ib(cls, execution, account, order):
        # filled = order.filledQuantity if order.filledQuantity < UNSET_DOUBLE else 0
        # Распарсить execution.time
        return cls(
            account=account,
            order=order,
            amount=execution.shares,
            price=execution.price,
            exec_id=execution.execId,
            exchange=execution.exchange,
            time=None,
            commission=0,  # приходит отдельно
        )

    class Meta:
        app_label = "main"
