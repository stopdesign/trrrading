from tortoise import models
from tortoise import fields


class Instrument(models.Model):
    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=50)
    main_exchange = fields.ForeignKeyField("models.Exchange", null=False)

    def __str__(self):
        return self.symbol

    class Meta:
        table = "main_instrument"
