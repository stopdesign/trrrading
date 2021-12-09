from django.apps import apps
from django.conf import settings
from django.urls import path, include, re_path
from django.views.static import serve
from django.contrib.staticfiles.views import serve as staticfiles_serve

from project.admin import admin_site
from project.views import server_error_emulate
from project.views import AccessDeniedView, PageNotFoundView, ServerErrorView


urlpatterns = [
    path("", include("main.urls")),
    path("admin/", admin_site.urls),
    # HTTP-500 emulation
    path(r"500-e/", server_error_emulate),
    # For reverse media url
    re_path(r"^(?P<path>favicon\.ico)$", staticfiles_serve, name="favicon"),
    re_path(
        r"^md/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
        name="media",
    ),
]


if settings.DEBUG:
    urlpatterns += [
        path("403/", AccessDeniedView.as_view()),
        path("404/", PageNotFoundView.as_view()),
        path("500/", ServerErrorView.as_view()),
    ]

handler403 = AccessDeniedView.as_view()
handler404 = PageNotFoundView.as_view()
handler500 = ServerErrorView.as_view()


# Change name for some apps
apps.get_app_config("main").verbose_name = "Mission"
