from django.db import models


class Instrument(models.Model):
    symbol = models.CharField(max_length=50)
    main_exchange = models.ForeignKey("Exchange", null=False, on_delete=models.PROTECT)
    multiplier = models.PositiveIntegerField(default=1)
    min_tick = models.DecimalField(default=0.01, max_digits=5, decimal_places=2)
    sec_type = models.CharField(max_length=50, default="")
    description = models.CharField(max_length=100, default="")

    def __str__(self):
        return f"{self.symbol}"
