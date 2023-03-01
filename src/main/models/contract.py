from django.db import models


class Contract(models.Model):

    class Type(models.TextChoices):
        fut = "FUT", "Futures"
        stk = "STK", "Equity"
        opt = "OPT", "Options",
        cash = "CASH", "Cash",

    conid = models.PositiveIntegerField(null=True)

    symbol = models.CharField(max_length=50)
    local_symbol = models.CharField(max_length=50, null=True)

    main_exchange = models.ForeignKey("Exchange", null=False, on_delete=models.PROTECT)
    multiplier = models.DecimalField(default=1, max_digits=10, decimal_places=4)
    min_tick = models.DecimalField(default=0.01, max_digits=8, decimal_places=4)
    sec_type = models.CharField(max_length=50, choices=Type.choices, default=Type.stk)

    def __str__(self):
        return f"{self.symbol}"

    @property
    def ticker(self):
        return f"{self.symbol}.{self.main_exchange.symbol}"

    @classmethod
    def from_ib(cls, contract):
        multiplier = contract.multiplier or 1
        return cls(
            conid = contract.conId,
            symbol = contract.symbol,
            local_symbol = contract.localSymbol,
            main_exchange_id = 1,
            multiplier = multiplier,
            min_tick = 0.01,
            sec_type = contract.secType,
        )

    class Meta:
        app_label = "main"
