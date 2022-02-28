from django.db import models


class Instrument(models.Model):
    class Type(models.TextChoices):
        fut = "FUT", "Futures"
        stk = "STK", "Equity"

    symbol = models.CharField(max_length=50)
    main_exchange = models.ForeignKey("Exchange", null=False, on_delete=models.PROTECT)
    multiplier = models.DecimalField(default=1, max_digits=10, decimal_places=4)
    min_tick = models.DecimalField(default=0.01, max_digits=5, decimal_places=2)
    sec_type = models.CharField(max_length=50, choices=Type.choices, default=Type.stk)
    description = models.CharField(max_length=100, default="")
    conid = models.PositiveIntegerField(null=True)

    def __str__(self):
        return f"{self.symbol}"

    class Meta:
        app_label = "main"
