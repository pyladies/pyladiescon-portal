from django.contrib import admin

from .models import Role, Team, VolunteerProfile


class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "user__first_name",
        "user__last_name",
        "user__email",
        "region",
        "availability_hours_per_week",
        "application_status",
        "creation_date",
        "modified_date",
    )
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "region",
        "application_status",
    )
    list_filter = ("region", "application_status")


admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
