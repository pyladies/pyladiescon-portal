from django.contrib import admin

from .models import PretixOrder


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
