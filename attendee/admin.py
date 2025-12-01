from django.contrib import admin

from .models import AttendeeProfile, PretixOrder


@admin.register(PretixOrder)
class PretixOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_code",
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
    list_filter = ("status", "is_anonymous")
    search_fields = ("order_code", "email", "name")


@admin.register(AttendeeProfile)
class AttendeeProfileAdmin(admin.ModelAdmin):
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
