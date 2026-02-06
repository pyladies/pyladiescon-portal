from django.contrib import admin

from .models import Event

class EventAdmin(admin.ModelAdmin):
    list_display = ("event_slug",)
    search_fields = ("event_slug",)
    # list_filter = ("region", "application_status")

admin.site.register(Event, EventAdmin)
