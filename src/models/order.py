from tortoise import models
from tortoise import fields


class Order(models.Model):
    """
    По-человечески это ордер в IB.
    Данные приходят в классе Trade.
    """
    id = fields.IntField(pk=True)
    order_id = fields.IntField(default=0)
    uid = fields.IntField(default=0)
    instrument = fields.ForeignKeyField('models.Instrument', related_name='orders')
    amount = fields.IntField(default=0)
    filled = fields.IntField(default=0)
    action = fields.CharField(max_length=50)
    type = fields.CharField(max_length=50)
    sig_price = fields.DecimalField(max_digits=10, decimal_places=2)
    lmt_price = fields.DecimalField(max_digits=10, decimal_places=2)
    avg_fill_price = fields.DecimalField(max_digits=10, decimal_places=2)
    is_bot = fields.BooleanField(default=False)
    status = fields.CharField(max_length=50)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"{self.action} {self.instrument}, {self.amount}"

    class Meta:
        table = "main_order"
