from django.urls import path

from main import views

app_name = "main"

urlpatterns = [
    # dashboard
    path("", views.dashboard, name="dashboard"),
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
