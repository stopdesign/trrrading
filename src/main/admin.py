import json
from decimal import Decimal

from django.contrib import admin
from django.forms import widgets

from project.admin import admin_site
from project.helpers.admin_decorators import boolean, short_description

from .models import Account, Contract, Order, OrderEvent, Position, Trade


class PrettyJSONWidget(widgets.Textarea):
    def format_value(self, value):
        try:
            value = json.dumps(json.loads(value), indent=4, ensure_ascii=False)
            # these lines will try to adjust size of TextArea to fit to content
            row_lengths = [len(r) for r in value.split("\n")]
            self.attrs["rows"] = min(max(len(row_lengths) + 2, 3), 25)
            self.attrs["cols"] = min(max(max(row_lengths) + 2, 75), 100)
            self.attrs["style"] = "font-family: monospace"
            self.attrs["spellcheck"] = "false"
            return value
        except Exception as e:
            # logger.warning("Error while formatting JSON: {}".format(e))
            return super(PrettyJSONWidget, self).format_value(value)


@admin.register(Account, site=admin_site)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "uid",
        "paper",
        "username",
        "net_value",
        "ex_liq_sec",
        "ex_liq_com",
        "updated_at",
    )
    actions_on_top = False
    actions = None


@admin.register(Contract, site=admin_site)
class ContractAdmin(admin.ModelAdmin):
    list_display = (
        "sid",
        "sec_type",
        "min_tick",
        "multiplier",
        "price_magnifier",
    )
    list_filter = ("sec_type",)
    actions_on_top = False
    actions_on_bottom = True
    # actions = None


class TradeInline(admin.TabularInline):
    model = Trade
    readonly_fields = (
        "order",
        "amount",
        "price",
        "exec_id",
        "commission",
        "time",
    )
    # readonly_fields =
    extra = 0


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    readonly_fields = (
        "status",
        "message",
        "time",
        "created_at",
    )
    extra = 0


@admin.register(Order, site=admin_site)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "local_id",
        "account",
        "contract",
        "get_status_bool",
        "status",
        "amount",
        "filled",
        "get_rth",
        "tif",
        "oca_group",
        "type",
        "action",
        "stop_price",
        "limit_price",
        "avg_fill_price",
        "created_at",
        "updated_at",
    )
    fields = (
        "amount",
        "filled",
        "status",
        "system_comment",
        "order_settings",
        "raw",
    )
    list_filter = (
        "account",
        "contract",
        "status",
        "created_at",
    )
    actions_on_top = False
    actions_on_bottom = True
    # actions = None
    inlines = [TradeInline]

    @boolean
    @short_description("")
    def get_status_bool(self, obj):
        status = None
        if obj.status in ["Filled"]:
            status = True
        if obj.status in ["Cancelled", "Error", "Failed", "Inactive"]:
            status = False
        return status

    @short_description("rth only")
    def get_rth(self, obj):
        return "no" if obj.outside_rth else "yes"

    @short_description("commission")
    def get_commission(self, obj):
        trades = obj.trades.all()
        commission = Decimal(0)
        for trade in trades:
            commission += trade.commission
        return commission

    @short_description("duration")
    def get_duration(self, obj):
        if obj.status != "Filled":
            return None
        last_trade = obj.trades.last()
        if last_trade:
            return int((last_trade.time - obj.created_at).total_seconds() - 32400)

    @short_description("slippage")
    def get_slippage(self, obj):
        if not (obj.signal_price and obj.avg_fill_price):
            return None
        if obj.action.lower() == "sell":
            slippage = obj.signal_price - obj.avg_fill_price
        else:
            slippage = obj.avg_fill_price - obj.signal_price
        if slippage >= 0:
            slippage = f"+{slippage}"
        else:
            slippage = f"−{abs(slippage)}"
        return slippage

    def has_add_permission(self, request):
        return False

    # def has_change_permission(self, request, obj=None):
    #     return False

    # def has_delete_permission(self, request, obj=None):
    #     return False

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == "raw":
            kwargs["widget"] = PrettyJSONWidget
        return super().formfield_for_dbfield(db_field,**kwargs)


@admin.register(Position, site=admin_site)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "contract",
        "amount",
        "avg_price",
        "unrealized_pnl",
        "updated_at",
    )
    list_filter = ("account",)
    actions_on_top = False
    actions_on_bottom = True
    # actions = None


@admin.register(Trade, site=admin_site)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "amount",
        "price",
        "exec_id",
        "time",
        "commission",
        "created_at",
    )
    actions_on_top = False
    actions_on_bottom = True
