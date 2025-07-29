from django.contrib import admin

from .models import SponsorshipProfile

@admin.register(SponsorshipProfile)
class SponsorshipProfileAdmin(admin.ModelAdmin):
    list_display = ('organization_name', 'main_contact_user','sponsorship_type', 'application_status')
    list_filter = ('sponsorship_type', 'application_status', 'sponsorship_tier')
    search_fields = ('sponsor_organization_name', 'main_contact__username')
