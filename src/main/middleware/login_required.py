import logging
from django.conf import settings
from django.contrib.auth.views import LoginView
from django.http import HttpResponseForbidden
from django.urls import resolve

logger = logging.getLogger(__name__)


class NewLoginForm(LoginView):
    template_name = "signin.html"

    def get_success_url(self):
        return self.request.path


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.response = get_response

    def __call__(self, request):
        resolver = resolve(request.path)
        ignore_views = getattr(settings, "LOGIN_REQUIRED_IGNORE_VIEW_NAMES", [])

        if resolver.view_name in ignore_views:
            # Request view name mathces with an exception
            return self.response(request)
        elif request.user and request.user.is_authenticated:
            # User is authenticated
            return self.response(request)
        else:
            if "application/json" in request.headers.get("Accept", ""):
                # Return HTTP-403
                return HttpResponseForbidden("{}")
            else:
                # Render signin page
                response = NewLoginForm.as_view()(request)
                if hasattr(response, "render"):
                    print("response.render()", request.user)
                    return response.render()
                else:
                    print("else")
                    return response
