from django.urls import path, re_path

from main import views

app_name = "main"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("dash/positions", views.positions, name="positions"),
    path("dash/account", views.account, name="account"),
    path("dash/orders", views.orders, name="orders"),

    path("bt/", views.backtest, name="backtest"),
    path("bt/raw", views.bt_raw, name="bt_raw"),
    path("bt/events", views.bt_events, name="bt_events"),
    path("bt/results", views.results, name="results"),
    path("bt/strategies", views.strategies, name="strategies"),
]
