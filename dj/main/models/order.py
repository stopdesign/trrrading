from django.db import models


class Order(models.Model):

    class Side(models.TextChoices):
        buy = "BUY", "Buy"
        sell = "SELL", "Sell"

    instrument = models.ForeignKey("Instrument", null=False, on_delete=models.PROTECT)
    action = models.CharField(max_length=50, choices=Side.choices, null=True)

    order_id = models.IntegerField(default=0)
    uid = models.PositiveIntegerField(default=0, unique=True)
    amount = models.PositiveIntegerField(default=0)
    filled = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=50, null=True)
    sig_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    lmt_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    avg_fill_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    is_bot = models.BooleanField(default=False)
    status = models.CharField(max_length=50, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.instrument} {self.action} {self.amount}"
