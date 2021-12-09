from django.db import models


class Instrument(models.Model):
    symbol = models.CharField(max_length=50)
    main_exchange = models.ForeignKey("Exchange", null=False, on_delete=models.PROTECT)

    def __str__(self):
        return self.symbol
