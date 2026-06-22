from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from portal.models import Conference

from .models import IndividualDonation, SponsorshipProfile, SponsorshipTier


@admin.register(IndividualDonation)
class IndividualDonationAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_id",
        "conference",
        "donor_name",
        "donor_email",
        "donation_amount",
        "transaction_date",
        "is_anonymous",
    )
    list_filter = ("conference", "is_anonymous")
    search_fields = ("donor_name", "donor_email", "transaction_id")


@admin.register(SponsorshipTier)
class SponsorshipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "conference", "amount", "description")
    list_filter = ("conference", "name")
    search_fields = ("name", "description")


class SponsorshipProfileResource(resources.ModelResource):
    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True
        # Imports predate Phase 5's explicit conference column; tie rows to the
        # active edition so the now-required conference FK is satisfied.
        if instance.conference_id is None:
            instance.conference = Conference.get_active()

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
        "conference",
        "sponsor_contact_name",
        "sponsors_contact_email",
        "sponsorship_tier",
        "progress_status",
        "sponsorship_override_amount",
        "github_issue_url",
        "po_number",
        "main_contact_user",
    )
    list_filter = (
        "conference",
        "progress_status",
        "sponsorship_tier",
    )
    search_fields = ("organization_name",)
    fields = (
        "conference",
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
        "github_issue_url",
        "main_contact_user",
    )
    resource_classes = [SponsorshipProfileResource]
