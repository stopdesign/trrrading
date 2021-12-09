from tortoise import models
from tortoise import fields


class Exchange(models.Model):
    id = fields.IntField(pk=True)
    symbol = fields.CharField(max_length=50)
    name = fields.CharField(max_length=50)

    def __str__(self):
        return self.name

    class Meta:
        table = "main_exchange"
