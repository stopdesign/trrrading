from tortoise import models
from tortoise import fields


class Instrument(models.Model):
    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=50)
    main_exchange = fields.ForeignKeyField("models.Exchange", null=False)
    multiplier = fields.IntField(default=1)
    min_tick = fields.DecimalField(default=0.01, max_digits=5, decimal_places=2)
    sec_type = fields.CharField(max_length=50, default="")
    description = fields.CharField(max_length=100, default="")

    def __str__(self):
        return self.symbol

    class Meta:
        table = "main_instrument"
