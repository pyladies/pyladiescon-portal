from django.contrib import admin

from .models import Role, Team, VolunteerProfile


class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "timezone", "application_status")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("timezone", "application_status")


admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
