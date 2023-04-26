from decimal import Decimal

from django.db import models


class Contract(models.Model):
    class Type(models.TextChoices):
        fut = "FUT", "Futures"
        stk = "STK", "Equity"
        opt = "OPT", "Options"
        cash = "CASH", "Cash"
        crypto = "CRYPTO", "Crypto"

    sid = models.CharField(max_length=50, default="", db_index=True)
    sec_type = models.CharField(max_length=50, choices=Type.choices, default=Type.stk)
    multiplier = models.DecimalField(
        default=Decimal(1), max_digits=10, decimal_places=4
    )
    min_tick = models.DecimalField(
        default=Decimal(0.01), max_digits=10, decimal_places=6
    )
    price_magnifier = models.PositiveIntegerField(default=1, null=False)

    def __str__(self):
        return self.sid

    @classmethod
    def from_ib(cls, contract, contract_details, sid):
        multiplier = contract.multiplier or 1
        return cls(
            sid=sid,
            multiplier=multiplier,
            min_tick=Decimal(contract_details.minTick),
            sec_type=contract.secType,
            price_magnifier=Decimal(contract_details.priceMagnifier),
        )

    class Meta:
        app_label = "main"
