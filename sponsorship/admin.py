from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from portal.admin_filters import ActiveConferenceFilter
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
    # Export/import the conference by its year rather than the surrogate pk.
    conference = Field(
        attribute="conference",
        column_name="conference",
        widget=ForeignKeyWidget(Conference, field="year"),
    )

    def before_save_instance(self, instance, row, **kwargs):
        # during 'confirm' step, dry_run is True
        instance.from_import_export = True
        # Rows that omit the conference column belong to the active edition.
        if instance.conference_id is None:
            instance.conference = Conference.get_active()

    class Meta:
        model = SponsorshipProfile
        fields = (
            "id",
            "conference",
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
        ActiveConferenceFilter,
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
