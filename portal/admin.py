from django.contrib import admin

from .models import Conference


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "slug", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("name", "year", "slug")
    ordering = ("-year",)
    prepopulated_fields = {"slug": ("name",)}
