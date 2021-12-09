from django.views.generic import TemplateView


class AccessDeniedView(TemplateView):
    template_name = '403.html'

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context, status=403)


class PageNotFoundView(TemplateView):
    template_name = '404.html'

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context, status=404)


class ServerErrorView(TemplateView):
    template_name = '500.html'

    def dispatch(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def get(self, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context, status=500)


def server_error_emulate(request, exception=None):
    return 1/0
