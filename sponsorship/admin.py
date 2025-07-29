from django.contrib import admin
from .models import SponsorshipProfile, SponsorshipTier

# Register your models here.
@admin.register(SponsorshipTier)
class SponsorshipTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount')
    search_fields = ('name',)
    ordering = ('amount',)

@admin.register(SponsorshipProfile)
class SponsorshipProfileAdmin(admin.ModelAdmin):
    list_display = ('sponsor_organization_name', 'main_contact','sponsorship_type', 'application_status')
    list_filter = ('sponsorship_type', 'application_status', 'sponsorship_tier')
    search_fields = ('sponsor_organization_name', 'main_contact__username')
