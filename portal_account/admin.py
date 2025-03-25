from django.contrib import admin
from .models import PortalProfile


class PortalProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "user__first_name",
        "user__last_name",
        "pronouns",
        "coc_agreement",
    )
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("pronouns", "coc_agreement")


admin.site.register(PortalProfile, PortalProfileAdmin)
