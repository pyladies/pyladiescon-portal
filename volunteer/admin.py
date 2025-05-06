from django.contrib import admin

from .constants import ApplicationStatus
from .models import Role, Team, VolunteerProfile


class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "timezone", "application_status")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("timezone", "application_status")

    def approve_volunteers(self, request, queryset):
        for profile in queryset:
            profile.application_status = ApplicationStatus.APPROVED
            profile.save()


admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
