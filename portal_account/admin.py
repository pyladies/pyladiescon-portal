from django.contrib import admin

from .models import PortalProfile


class PortalProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "get_first_name",  
        "get_last_name",
        "pronouns",
        "coc_agreement",
        "tos_agreement",
    )
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("pronouns", "coc_agreement", "tos_agreement")
    readonly_fields = ("coc_agreement", "tos_agreement")

    @admin.display(ordering="user__first_name", description="First Name")
    def get_first_name(self, obj):
        return obj.user.first_name

    @admin.display(ordering="user__last_name", description="Last Name")
    def get_last_name(self, obj):
        return obj.user.last_name

admin.site.register(PortalProfile, PortalProfileAdmin)
