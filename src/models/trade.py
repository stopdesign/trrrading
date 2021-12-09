from tortoise import models
from tortoise import fields


class Trade(models.Model):
    """
    Это execution-fill-commission вместе. Данные об исполнении ордера.
    """
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField('models.Order', related_name='trades')

    amount = fields.IntField(default=0)
    price = fields.DecimalField(default=0, max_digits=10, decimal_places=2)

    exec_id = fields.CharField(max_length=50, unique=True, null=True)
    exchange = fields.CharField(max_length=50)

    time = fields.DatetimeField(null=True)
    commission = fields.DecimalField(null=True, max_digits=10, decimal_places=2)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"{self.order.pk}, {self.amount}"

    class Meta:
        table = "main_trade"
