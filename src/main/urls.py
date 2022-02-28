from django.urls import path, re_path
from main import views

app_name = "main"

urlpatterns = [
    path("tv/history", views.history, name="history"),
    path("tv/time", views.time, name="time"),
    path("tv/symbols", views.symbols, name="symbols"),
    path("tv/config", views.config, name="config"),
    path("tv/marks", views.marks, name="marks"),
    path("tv/timescale_marks", views.timescale_marks, name="timescale_marks"),
    # path("api/save/<int:payload_id>/", save, name="api_save"),
    # path("api/load/<int:payload_id>/", load, name="api_load"),
    # path("company_profile/", CompanyProfileView.as_view(), name="company_profile"),
    # path("user_profile/", UserProfileView.as_view(), name="user_profile"),
    # path("logout/", LogoutView.as_view(), name="logout"),

    # re_path(
    #     r"^payload/(?P<payload_id>[0-9]+)/.*", PayloadView.as_view(), name="payload"
    # ),
]
