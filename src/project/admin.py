from django.contrib.admin import AdminSite


class CustomAdminSite(AdminSite):

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}

        # missions = Mission.objects.all().prefetch_related('vehicles')
        # extra_context.update({'missions': missions})

        return super(CustomAdminSite, self).index(request, extra_context)


admin_site = CustomAdminSite(name='admin')
