from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect, HttpResponse
from django.views import View
from django.views.generic import TemplateView, UpdateView


# class PayloadListView(TemplateView):
#     template_name = "payload_list.html"
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         company = self.request.user.company
#         context['payloads'] = Payload.objects.filter(customer=company)
#         return context
#
#
# class PayloadView(TemplateView):
#     template_name = "payload.html"
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         payload_id = kwargs.pop("payload_id")
#         context['payload'] = Payload.objects.get(id=payload_id)
#         return context

