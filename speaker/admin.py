from django.contrib import admin

from .models import SpeakerProfile

class SpeakerProfileAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "email")
    search_fields = ("code", "name", "email")
    # list_filter = ("region", "application_status")

admin.site.register(SpeakerProfile, SpeakerProfileAdmin)
