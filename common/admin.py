from django.contrib import admin

from .models import SentEmail


@admin.register(SentEmail)
class SentEmailAdmin(admin.ModelAdmin):
    """Read-only: the record says what was sent, and nobody rewrites that.
    The Maintenance page is where it is read; this is the raw view."""

    list_display = ("sent_at", "to", "subject", "template", "status", "conference")
    list_filter = ("status", "conference", "template")
    search_fields = ("to", "subject")
    date_hierarchy = "sent_at"
    list_select_related = ("conference",)
    readonly_fields = [f.name for f in SentEmail._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
