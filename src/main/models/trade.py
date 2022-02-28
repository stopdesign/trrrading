from django.db import models


class Trade(models.Model):
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

    class Meta:
        app_label = "main"
