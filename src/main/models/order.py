import json
from secrets import token_hex
from django.db import models
from main.models import Contract


# UNSET_INTEGER = 2 ** 31 - 1  # 2147483647
# UNSET_DOUBLE = sys.float_info.max  # ~1.79e+308
# UNSET_LONG = 2 ** 63 - 1  # 9223372036854775807
# UNSET_DECIMAL = Decimal(2 ** 127 - 1)  # ~1.70e+38


def fix_float(value: float, default=None) -> float | None:
    if value >= 10**30:
        return default
    else:
        return value


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
        stp = "STP", "Stop"
        stp_lmt = "STP LMT", "Stop Limit"
        trl = "TRAIL", "Trail"
        trl_lmt = "TRAIL LIMIT", "Trail Limit"
        mid = "MIDPRICE", "MidPrice"

    account = models.ForeignKey("Account", null=True, on_delete=models.PROTECT)
    run = models.ForeignKey("Run", null=True, on_delete=models.CASCADE, related_name="orders")

    contract = models.ForeignKey("Contract", null=False, on_delete=models.PROTECT)
    action = models.CharField(max_length=50, choices=Side.choices, null=True)

    order_id = models.PositiveIntegerField(unique=True, null=True)  # perm id IBKR
    local_id = models.CharField(max_length=250, null=True)  # локальный id гейтвея

    amount = models.PositiveIntegerField(default=0)
    filled = models.PositiveIntegerField(default=0)
    type = models.CharField(max_length=50, choices=Type.choices, null=True)

    oca_group = models.PositiveIntegerField(null=True)

    algo_strategy = models.CharField(max_length=50, null=True)
    algo_params = models.CharField(max_length=200, null=True)

    signal_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    limit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    stop_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    trailing_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    trailing_percent = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    avg_fill_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status = models.CharField(max_length=50, null=True)
    raw = models.TextField(null=True)
    tif = models.CharField(max_length=10, null=True)
    outside_rth = models.BooleanField(default=False)

    # Настройки ордера, которые нужно пробрасывать из бота
    order_settings = models.CharField(max_length=500, null=True)

    # Всякие статусы, которые возвращаются брокером
    system_comment = models.CharField(max_length=500, null=True)

    # Строка orderDesc из IBKR
    string_repr = models.CharField(max_length=500, null=True)

    # Некий слепок ордера, по которому понимаем, что он изменился в IBKR
    version = models.CharField(max_length=50, null=True)

    created_at = models.DateTimeField(null=True, auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        return f"{self.contract} {self.action} {self.amount}"

    @classmethod
    def from_ib(cls, order, account, contract, state):
        order_type = order.orderType

        limit_price = fix_float(order.lmtPrice) or None
        stop_price = fix_float(order.trailStopPrice) or None

        if order_type in [Order.Type.trl_lmt, Order.Type.trl]:
            trailing_amount = fix_float(order.auxPrice) or None
            trailing_percent = fix_float(order.trailingPercent) or None
        else:
            trailing_amount = None
            trailing_percent = None

        total = fix_float(order.totalQuantity, 0)
        filled = fix_float(order.filledQuantity, 0)

        # У исполненного ордера нет totalQuantity, беру значение из filledQuantity
        if state.status == "Filled" and not total:
            total = filled

        try:
            oca_group = int(order.ocaGroup)
        except:
            oca_group = None

        return cls(
            order_id=order.permId,
            account=account,
            contract=contract,
            action=order.action,
            local_id=order.orderRef,
            status=state.status,
            amount=total,
            filled=filled,
            type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            trailing_amount=trailing_amount,
            trailing_percent=trailing_percent,
            outside_rth=order.outsideRth,
            raw=cls.format_raw(order),
            tif=order.tif,
            oca_group=oca_group,
            algo_strategy=order.algoStrategy,
            algo_params=order.algoParams,
        )

    @classmethod
    def format_raw(cls, order) -> str:
        """
        Поля объекта IB Order в виде json.
        """
        raw = json.dumps(order.__dict__, indent=2, default=str)
        raw = raw.replace(' "170141183460469231731687303715884105727"', " null")
        raw = raw.replace(" 1.7976931348623157e+308", " null")
        raw = raw.replace(" 9223372036854775807", " null")
        raw = raw.replace(" 2147483647", " null")
        return raw

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
    def market_order(cls, account, contract, side, amount):
        order = cls(
            account=account,
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
    def stop_order(cls, account, contract, side, amount):
        order = cls(
            account=account,
            contract=contract,
            action=side,
            local_id=new_local_id(),
            status="New",
            amount=amount,
            type=cls.Type.stp,
            is_bot=True,
        )
        return order

    @classmethod
    def adaptive_market_order(cls, account, contract, side, amount):
        order = cls.market_order(account, contract, side, amount)
        order.order_settings = '{"strategy": "Adaptive", "priority": "Normal"}'
        return order

    class Meta:
        app_label = "main"
