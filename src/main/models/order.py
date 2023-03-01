import sys
from datetime import timezone
from secrets import token_hex
from django.db import models
from main.models import Contract


UNSET_DOUBLE = sys.float_info.max


def dt_to_ts(dt):
    return int(dt.timestamp())


def new_local_id():
    return "bot_" + token_hex(4)


class Order(models.Model):

    class Side(models.TextChoices):
        buy = "BUY", "Buy"
        sell = "SELL", "Sell"

    class Type(models.TextChoices):
        mkt = "MKT", "Market"
        lmt = "LMT", "Limit"

    account = models.ForeignKey("Account", null=True, on_delete=models.PROTECT)
    run = models.ForeignKey("Run", null=True, on_delete=models.CASCADE, related_name="orders")

    contract = models.ForeignKey("Contract", null=False, on_delete=models.PROTECT)
    action = models.CharField(max_length=50, choices=Side.choices, null=True)

    order_id = models.PositiveIntegerField(unique=True, null=True)  # id IBKR
    local_id = models.CharField(max_length=250, null=True)  # локальный id гейтвея

    amount = models.PositiveIntegerField(default=0)
    filled = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=50, choices=Type.choices, null=True)
    signal_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    limit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    avg_fill_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    is_bot = models.BooleanField(default=False)
    status = models.CharField(max_length=50, null=True)
    outside_rth = models.BooleanField(default=False)

    # Настройки ордера, которые нужно пробрасывать из бота
    order_settings = models.CharField(max_length=500, null=True)

    # Всякие статусы, которые возвращаются брокером
    system_comment = models.CharField(max_length=500, null=True)

    # Строка orderDesc из IBKR
    string_repr = models.CharField(max_length=500, null=True)

    # Некий слепок ордера, по которому понимаем, что он изменился в IBKR
    version = models.CharField(max_length=50, null=True)

    created_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"{self.contract} {self.action} {self.amount}"

    @property
    def ticker(self):
        return f"{self.contract.ticker}"

    @classmethod
    def from_ib(cls, order, account, contract, state):
        order_type = order.orderType
        filled = order.filledQuantity if order.filledQuantity < UNSET_DOUBLE else 0
        return cls(
            order_id=order.permId,
            account=account,
            contract=contract,
            action=order.action,
            local_id=order.orderRef,
            status=state.status,
            amount=order.totalQuantity,
            filled=filled,
            type=cls.Type.lmt,
            limit_price=order.lmtPrice,
            is_bot=False,
            outside_rth=order.outsideRth,
        )

    @classmethod
    def limit_order(cls, account, contract, side, amount, price, outside_rth=False):
        if contract.sec_type == Contract.Type.fut and outside_rth:
            raise ValueError("Futures can't be outside_rth")
        order = cls(
            account=account,
            contract=contract,
            action=side,
            local_id=new_local_id(),
            status="New",
            amount=amount,
            type=cls.Type.lmt,
            limit_price=price,
            is_bot=True,
            outside_rth=outside_rth,
        )
        return order

    @classmethod
    def market_order(cls, account, run, contract, side, amount):
        order = cls(
            account=account,
            run=run,
            contract=contract,
            action=side,
            local_id=new_local_id(),
            status="New",
            amount=amount,
            type=cls.Type.mkt,
            is_bot=True,
        )
        return order

    @classmethod
    def adaptive_market_order(cls, account, run, contract, side, amount):
        order = cls.market_order(account, run, contract, side, amount)
        order.order_settings = '{"strategy": "Adaptive", "priority": "Normal"}'
        return order

    def simulate_fill(self, fill_price):
        self.avg_fill_price = fill_price
        self.filled = self.amount
        self.status = "Filled"
        self.save()

    def as_json(self):
        if self.avg_fill_price:
            price = float(self.avg_fill_price)
        else:
            price = float(self.signal_price)
        return {
            "id": self.id,
            "amount": self.amount,
            "side": self.action.lower(),
            "time": dt_to_ts(self.created_at),
            "dt": str(self.created_at),
            "price": price,
        }

    class Meta:
        app_label = "main"
