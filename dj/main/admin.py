import json
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import JSONField
from django.forms import widgets
from project.admin import admin_site
from project.helpers.admin_decorators import short_description
from .models import Exchange, Instrument, Order, Position, Trade, OrderEvent
# from .models import User
# from django.contrib.auth.models import User


class PrettyJSONWidget(widgets.Textarea):
    def format_value(self, value):
        try:
            value = json.dumps(json.loads(value), indent=4, ensure_ascii=False)
            # these lines will try to adjust size of TextArea to fit to content
            row_lengths = [len(r) for r in value.split("\n")]
            self.attrs["rows"] = min(max(len(row_lengths) + 2, 3), 10)
            self.attrs["cols"] = min(max(max(row_lengths) + 2, 75), 100)
            self.attrs["style"] = "font-family: monospace"
            self.attrs["spellcheck"] = "false"
            return value
        except Exception as e:
            # logger.warning("Error while formatting JSON: {}".format(e))
            return super(PrettyJSONWidget, self).format_value(value)


# @admin.register(Payload, site=admin_site)
# class PayloadAdmin(CompareVersionAdmin):
#     list_display = ["name", "type", "customer", "vehicle", "created_at"]
#     list_filter = ("customer", "vehicle", "type")
#     change_form_template = "admin/payload_change_form.html"
#
#     formfield_overrides = {JSONField: {"widget": PrettyJSONWidget}}
#
#     actions_on_top = False
#     actions = None


# @admin.register(User, site=admin_site)
# class UserAdmin(UserAdmin):
#     fieldsets = (
#         (None, {"fields": ("email", "password")}),
#         (_("Personal info"), {"fields": ("full_name", "phone", "company")}),
#         (
#             _("Permissions"),
#             {
#                 "fields": (
#                     "is_active",
#                     "is_staff",
#                     "is_superuser",
#                 ),
#             },
#         ),
#         (_("Important dates"), {"fields": ("last_login", "date_joined")}),
#     )
#     add_fieldsets = (
#         (
#             None,
#             {
#                 "classes": ["wide"],
#                 "fields": ("email", "password1", "password2", "company"),
#             },
#         ),
#     )
#     list_display = ("email", "full_name", "company", "is_staff")
#     list_filter = ("company", "is_active", "is_staff", "is_superuser")
#     search_fields = ()
#     ordering = ("-id",)
#     actions_on_top = False
#     actions = None


# "Exchange", "Instrument", "Order", "Position", "Trade"


@admin.register(Exchange, site=admin_site)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "name",
    )
    actions_on_top = False
    actions = None


@admin.register(Instrument, site=admin_site)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "main_exchange",
        "description",
        "min_tick",
        "sec_type",
        "multiplier",
    )
    actions_on_top = False
    actions = None


class TradeInline(admin.TabularInline):
    model = Trade
    readonly_fields = (
        "order",
        "amount",
        "price",
        "exec_id",
        "exchange",
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
        "instrument",
        "order_id",
        "uid",
        "amount",
        "filled",
        "type",
        "action",
        # "lmt_price",
        "sig_price",
        "avg_fill_price",
        "get_slippage",
        "get_commission",
        "get_duration",
        "status",
        "created_at",
    )
    fields = (
        "instrument",
        "action",
        "amount",
        "filled",
        "status",
    )
    list_filter = (
        "instrument",
        "created_at",
    )
    actions_on_top = False
    actions_on_bottom = True
    # actions = None
    inlines = [TradeInline, OrderEventInline]

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
        return int((last_trade.time - obj.created_at).total_seconds() - 32400)

    @short_description("slippage")
    def get_slippage(self, obj):
        if not (obj.sig_price and obj.avg_fill_price):
            return None
        if obj.action.lower() == "sell":
            slippage = obj.sig_price - obj.avg_fill_price
        else:
            slippage = obj.avg_fill_price - obj.sig_price
        if slippage >= 0:
            slippage = f"+{slippage}"
        else:
            slippage = f"−{abs(slippage)}"
        return slippage

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Position, site=admin_site)
class PositionAdmin(admin.ModelAdmin):
    actions_on_top = False
    actions = None


@admin.register(Trade, site=admin_site)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "amount",
        "price",
        "exec_id",
        "exchange",
        "time",
        "commission",
        "created_at",
    )
    actions_on_top = False
    actions_on_bottom = True


# @admin.register(Mission, site=admin_site)
# class MissionAdmin(CompareVersionAdmin):
#     list_display = (
#         "name", "launch_id", "provider",
#         "vehicle", "period_start",
#         "period_end", "orbit",
#         "apogee", "perigee",
#     )
#     actions_on_top = False
#     actions = None
#
#
# @admin.register(Vehicle, site=admin_site)
# class VehicleAdmin(CompareVersionAdmin):
#     actions_on_top = False
#     actions = None
#     list_display = [
#         "program_id", "name", "mission", "vehicle",
#         "vehicle_class", "block", "config_id"
#     ]
#     list_filter = ["mission"]
