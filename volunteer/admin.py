from django.contrib import admin

from .constants import ApplicationStatus
from .models import Role, Team, VolunteerProfile


@admin.action(description="Mark selected Volunteers as waitlisted")
def bulk_waitlist_volunteers(modeladmin, request, queryset):
    """Waitlist the volunteers one by one.

    We want to trigger the email notification signal for each volunteers this way.
    """
    for volunteer in queryset:
        volunteer.application_status = ApplicationStatus.WAITLISTED
        volunteer.save()


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
    actions = [bulk_waitlist_volunteers]


admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
