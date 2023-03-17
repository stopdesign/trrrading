from django.urls import path, re_path
from main import views

app_name = "main"

urlpatterns = [
    path("md/", views.data_inspector, name="data_inspector"),
    path("md/dash.csv", views.market_data_status_api, name="market_data_status_api"),

    path("dash/", views.dashboard, name="dashboard"),
    path("dash/positions", views.positions, name="positions"),
    path("dash/account", views.account, name="account"),
    path("dash/orders", views.orders, name="orders"),

    path("bt/", views.backtest, name="backtest"),
    path("bt/raw", views.bt_raw, name="bt_raw"),
    path("bt/events", views.bt_events, name="bt_events"),
    path("bt/results", views.results, name="results"),
    path("bt/strategies", views.strategies, name="strategies"),
    path("bt/history", views.backtest_data, name="backtest_data"),
    path("bt/config", views.config, name="config"),
    path("bt/symbols", views.symbols, name="symbols"),

    path("tv/history", views.history, name="history"),
    path("tv/time", views.time, name="time"),
    path("tv/symbols", views.symbols, name="symbols"),
    path("tv/config", views.config, name="config"),

    # path("api/save/<int:payload_id>/", save, name="api_save"),
    # path("api/load/<int:payload_id>/", load, name="api_load"),
    # path("company_profile/", CompanyProfileView.as_view(), name="company_profile"),
    # path("user_profile/", UserProfileView.as_view(), name="user_profile"),
    # path("logout/", LogoutView.as_view(), name="logout"),

    # re_path(
    #     r"^payload/(?P<payload_id>[0-9]+)/.*", PayloadView.as_view(), name="payload"
    # ),
]
