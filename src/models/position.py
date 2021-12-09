from tortoise import models
from tortoise import fields


class Position(models.Model):
    id = fields.IntField(pk=True)
    instrument = fields.ForeignKeyField("models.Instrument", null=False)
    amount = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "main_position"
