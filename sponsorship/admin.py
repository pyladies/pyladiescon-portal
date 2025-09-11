from django.contrib import admin

from .models import SponsorshipProfile, SponsorshipTier


@admin.register(SponsorshipTier)
class SponsorshipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "description")
    list_filter = ("name",)
    search_fields = ("name", "description")


@admin.register(SponsorshipProfile)
class SponsorshipProfileAdmin(admin.ModelAdmin):
    list_display = (
        "organization_name",
        "main_contact_user",
        "sponsorship_tier", 
        "application_status",
    )
    list_filter = ("application_status", "sponsorship_tier") 
    search_fields = ("organization_name", "main_contact_user")