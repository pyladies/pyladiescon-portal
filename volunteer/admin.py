from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .constants import ApplicationStatus
from .models import Language, PyladiesChapter, Role, Team, VolunteerProfile


@admin.action(description="Mark selected Volunteers as waitlisted")
def bulk_waitlist_volunteers(modeladmin, request, queryset):
    """Waitlist the volunteers one by one.

    We want to trigger the email notification signal for each volunteers this way.
    """
    for volunteer in queryset:
        volunteer.application_status = ApplicationStatus.WAITLISTED
        volunteer.save()


class VolunteerProfileResource(resources.ModelResource):
    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True

    class Meta:
        model = VolunteerProfile
        fields = (
            "id",
            "user__first_name",
            "user__last_name",
            "user__email",
            "application_status",
            "github_username",
            "discord_username",
            "instagram_username",
            "bluesky_username",
            "mastodon_url",
            "x_username",
            "linkedin_url",
            "region",
            "chapter__chapter_name",
        )


class VolunteerProfileAdmin(ImportExportModelAdmin):
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
    resource_classes = [VolunteerProfileResource]


class PyladiesChapterResource(resources.ModelResource):
    class Meta:
        model = PyladiesChapter
        fields = (
            "id",
            "chapter_name",
            "chapter_description",
            "chapter_email",
            "chapter_website",
        )


@admin.register(PyladiesChapter)
class PyladiesChapterAdmin(ImportExportModelAdmin):
    list_display = (
        "chapter_name",
        "chapter_description",
        "chapter_email",
        "chapter_website",
        "has_logo",
    )
    resource_classes = [PyladiesChapterResource]
    search_fields = ["chapter_name", "chapter_description", "chapter_email"]

    def has_logo(self, obj):
        """Returns True if the chapter has a logo uploaded."""
        if obj.logo:
            return True
        else:
            return False

    has_logo.boolean = True  # Render the has_logo column with a check icon
    has_logo.short_description = "Has Logo"


admin.site.register(Role)
admin.site.register(Team)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
admin.site.register(Language)
