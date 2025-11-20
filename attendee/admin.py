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
        "job_role",
        "country",
        "region",
        "experience_level",
        "industry",
    )
    list_filter = ("job_role", "country", "region", "experience_level", "industry")
    search_fields = ("order__order_code", "job_role", "country")
    readonly_fields = ("raw_answers",)
