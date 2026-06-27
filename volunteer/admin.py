from django.contrib import admin, messages
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from portal.admin_filters import ActiveConferenceFilter
from portal.models import Conference

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


@admin.action(description="Bring selected volunteers forward to the active conference")
def bring_forward_to_active_conference(modeladmin, request, queryset):
    """Carry returning volunteers into the active edition without re-applying.

    Copies each selected profile's details into a new PENDING profile for the
    active conference; volunteers who already have a profile there are skipped.
    """
    active = Conference.get_active()
    if active is None:
        modeladmin.message_user(
            request, "No active conference is set.", level=messages.ERROR
        )
        return
    created = 0
    skipped = 0
    for volunteer in queryset:
        if volunteer.bring_forward_to(active) is None:
            skipped += 1
        else:
            created += 1
    modeladmin.message_user(
        request,
        f"Brought {created} volunteer(s) forward into {active}; "
        f"{skipped} already had a profile there.",
        level=messages.SUCCESS,
    )


class VolunteerProfileResource(resources.ModelResource):
    # Export/import the conference by its year (stable, human-readable) rather
    # than the surrogate pk.
    conference = Field(
        attribute="conference",
        column_name="conference",
        widget=ForeignKeyWidget(Conference, field="year"),
    )

    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True
        # Rows that omit the conference column belong to the active edition.
        if instance.conference_id is None:
            instance.conference = Conference.get_active()

    class Meta:
        model = VolunteerProfile
        fields = (
            "id",
            "conference",
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
        "conference",
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
    list_filter = (ActiveConferenceFilter, "region", "application_status")
    actions = [bulk_waitlist_volunteers, bring_forward_to_active_conference]
    resource_classes = [VolunteerProfileResource]
    # Dual-list ("available"/"chosen") pickers for the many-to-many fields.
    filter_horizontal = ("teams", "roles", "language")
    # ``languages_spoken`` is deprecated in favour of the ``language`` m2m; hide
    # it from the admin form (the public form already excludes it).
    exclude = ("languages_spoken",)


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


class TeamAdmin(admin.ModelAdmin):
    list_display = ("short_name", "conference", "open_to_new_members")
    list_filter = ("conference", "open_to_new_members")
    search_fields = ("short_name", "description")


admin.site.register(Role)
admin.site.register(Team, TeamAdmin)
admin.site.register(VolunteerProfile, VolunteerProfileAdmin)
admin.site.register(Language)
