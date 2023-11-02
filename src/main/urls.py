from django.urls import path
from main.sockets import ChatConsumer

from main import views
from main.views_pnl import pnl_report

app_name = "main"


ws_urlpatterns = [
    path(r"ws/chat", ChatConsumer.as_asgi()),
]

urlpatterns = [
    # dashboard
    path("", views.dashboard, name="dashboard"),
    path("dash/pnl", pnl_report, name="pnl_report"),
    path("dash/positions", views.positions, name="positions"),
    path("dash/account", views.account, name="account"),
    path("dash/orders", views.orders, name="orders"),
    # backtest
    path("bt/", views.backtest, name="backtest"),
    path("bt/meta", views.bt_meta, name="bt_meta"),
    path("bt/ohlc", views.bt_ohlc, name="bt_raw"),
    path("bt/events", views.bt_events, name="bt_events"),
    path("bt/results", views.bt_results, name="bt_results"),
    path("bt/strategies", views.bt_strategies, name="bt_strategies"),
]
