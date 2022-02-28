from django.db import models


class Position(models.Model):
    account = models.ForeignKey("Account", null=False, on_delete=models.PROTECT)

    instrument = models.ForeignKey("Instrument", null=False, on_delete=models.PROTECT)
    amount = models.IntegerField(default=0)
    avg_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    unrealized_pnl = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account} {self.instrument}"

    class Meta:
        app_label = "main"
