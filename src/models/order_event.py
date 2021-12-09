from tortoise import models
from tortoise import fields


class OrderEvent(models.Model):
    id = fields.IntField(pk=True)
    order = fields.ForeignKeyField("models.Order")
    status = fields.CharField(max_length=50, null=True)
    message = fields.CharField(max_length=100, null=True)
    time = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order} {self.status} {self.message}"

    class Meta:
        table = "main_orderevent"
