from django.contrib import admin

from .models import SpeakerSettings


@admin.register(SpeakerSettings)
class SpeakerSettingsAdmin(admin.ModelAdmin):
    list_display = ("conference", "speaker_module_enabled")
    list_filter = ("speaker_module_enabled",)
    list_select_related = ("conference",)
