from django.db import models


class Account(models.Model):
    uid = models.CharField(max_length=50, unique=True)
    paper = models.BooleanField(default=False)

    net_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    margin_used = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cash_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ex_liq_sec = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ex_liq_com = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    daily_pnl = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unrealized_pnl = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.uid

    class Meta:
        app_label = "main"
