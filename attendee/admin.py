from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from .models import AttendeeProfile, PretixOrder


@admin.register(PretixOrder)
class PretixOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_code",
        "conference",
        "status",
        "email",
        "name",
        "total",
        "datetime",
        "cancellation_date",
        "last_modified",
        "url",
        "is_anonymous",
    )
    list_filter = ("conference", "status", "is_anonymous")
    search_fields = ("order_code", "email", "name")


class AttendeeProfileResource(resources.ModelResource):
    # Attendees inherit their conference from the order; export the year as a
    # read-only column (it is never imported back onto the profile). Both
    # ``order`` and ``order.conference`` are non-null, so the path is safe.
    conference = Field(column_name="conference", readonly=True)

    def dehydrate_conference(self, obj):
        return obj.order.conference.year

    class Meta:
        model = AttendeeProfile
        fields = (
            "order",
            "conference",
            "order__name",
            "order__email",
            "order__status",
            "may_share_email_with_sponsor",
            "chapter_description",
            "chapter_email",
            "chapter_website",
        )


@admin.register(AttendeeProfile)
class AttendeeProfileAdmin(ImportExportModelAdmin):
    list_display = (
        "order",
        "city",
        "country",
        "current_position",
        "experience_level",
        "may_share_email_with_sponsor",
        "pyladies_chapter",
        "age_range",
        "organization_name",
    )
    list_filter = (
        "country",
        "experience_level",
        "may_share_email_with_sponsor",
        "age_range",
    )
    search_fields = (
        "order__order_code",
        "current_position",
        "country",
        "city",
        "participated_in_previous_event",
    )
    readonly_fields = ("raw_answers",)
    resource_classes = [AttendeeProfileResource]
