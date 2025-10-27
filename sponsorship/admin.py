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
        "sponsor_contact_name",
        "sponsors_contact_email",
        "sponsorship_tier",
        "progress_status",
        "sponsorship_override_amount",
        "main_contact_user",
    )
    list_filter = (
        "progress_status",
        "sponsorship_tier",
    )
    search_fields = ("organization_name",)
    fields = (
        "organization_name",
        "sponsor_contact_name",
        "sponsors_contact_email",
        "sponsorship_tier",
        "sponsorship_override_amount",
        "organization_address",
        "logo",
        "company_description",
        "progress_status",
        "main_contact_user",
    )
