from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import IndividualDonation, SponsorshipProfile, SponsorshipTier


@admin.register(IndividualDonation)
class IndividualDonationAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "donor_name",
        "donor_email",
        "donation_amount",
        "transaction_date",
        "is_anonymous",
    )
    list_filter = ("is_anonymous",)
    search_fields = ("donor_name", "donor_email", "transaction_id")


@admin.register(SponsorshipTier)
class SponsorshipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "description")
    list_filter = ("name",)
    search_fields = ("name", "description")


class SponsorshipProfileResource(resources.ModelResource):
    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True

    class Meta:
        model = SponsorshipProfile
        fields = (
            "id",
            "organization_name",
            "sponsor_contact_name",
            "sponsors_contact_email",
            "sponsorship_tier",
            "progress_status",
            "sponsorship_override_amount",
            "po_number",
            "main_contact_user",
        )


@admin.register(SponsorshipProfile)
class SponsorshipProfileAdmin(ImportExportModelAdmin):
    list_display = (
        "organization_name",
        "sponsor_contact_name",
        "sponsors_contact_email",
        "sponsorship_tier",
        "progress_status",
        "sponsorship_override_amount",
        "po_number",
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
        "po_number",
        "organization_address",
        "logo",
        "company_description",
        "progress_status",
        "main_contact_user",
    )
    resource_classes = [SponsorshipProfileResource]
