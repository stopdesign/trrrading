from datetime import timezone
from secrets import token_hex
from django.db import models

from main.models import Instrument


def dt_to_ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class Order(models.Model):

    class Side(models.TextChoices):
        buy = "BUY", "Buy"
        sell = "SELL", "Sell"

    class Type(models.TextChoices):
        mkt = "MKT", "Market"
        lmt = "LMT", "Limit"

    account = models.ForeignKey("Account", null=False, on_delete=models.PROTECT)
    run = models.ForeignKey("Run", null=True, on_delete=models.CASCADE, related_name="orders")

    instrument = models.ForeignKey("Instrument", null=False, on_delete=models.PROTECT)
    action = models.CharField(max_length=50, choices=Side.choices, null=True)

    order_id = models.PositiveIntegerField(unique=True, null=True)  # id IBKR
    local_id = models.CharField(max_length=50, null=True)  # локальный id гейтвея

    amount = models.PositiveIntegerField(default=0)
    filled = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=50, choices=Type.choices, null=True)
    signal_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    limit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    avg_fill_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    is_bot = models.BooleanField(default=False)
    status = models.CharField(max_length=50, null=True)
    outside_rth = models.BooleanField(default=False)

    # Некий слепок ордера, по которому понимаем, что он изменился в IBKR
    version = models.CharField(max_length=50, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"{self.instrument} {self.action} {self.amount}"

    @classmethod
    def limit_order(cls, account, instrument, side, amount, price, outside_rth=False):
        if instrument.sec_type == Instrument.Type.fut and outside_rth:
            raise ValueError("Futures can't be outside_rth")
        order = cls(
            account=account,
            instrument=instrument,
            action=side,
            local_id=token_hex(4),
            status="New",
            amount=amount,
            type=cls.Type.lmt,
            limit_price=price,
            is_bot=True,
            outside_rth=outside_rth,
        )
        return order

    @classmethod
    def market_order(cls, account, run, instrument, side, amount):
        order = cls(
            account=account,
            run=run,
            instrument=instrument,
            action=side,
            local_id=token_hex(4),
            status="New",
            amount=amount,
            type=cls.Type.mkt,
            is_bot=True,
        )
        return order

    # @classmethod
    # def ibalgo_order(cls, instrument, side, amount, cap_price):
    #     order = cls(
    #         order_id=token_hex(4),
    #         status="New",
    #     )

    def as_json(self):
        return {
            "amount": self.amount,
            "side": self.action.lower(),
            "time": dt_to_ts(self.created_at),
            "price": float(self.avg_fill_price),
        }

    class Meta:
        app_label = "main"
