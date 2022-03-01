from secrets import token_hex
from django.db import models


def generate_uid():
    return token_hex(4)


class Run(models.Model):
    uid = models.CharField(max_length=50, unique=True, default=generate_uid)

    backtest = models.BooleanField(default=True)
    account = models.ForeignKey("Account", null=True, on_delete=models.PROTECT)

    description = models.CharField(max_length=100)

    broker_config = models.TextField(null=True)
    strategy_config = models.TextField(null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    finished_at = models.DateTimeField(null=True)

    from_dt = models.DateTimeField(null=True)
    start_dt = models.DateTimeField(null=True)
    end_dt = models.DateTimeField(null=True)

    def __str__(self):
        return self.uid

    class Meta:
        app_label = "main"
