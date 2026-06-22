from django.core import mail
from tablib import Dataset

from portal.models import Conference
from sponsorship.admin import SponsorshipProfileResource
from sponsorship.models import (
    SponsorshipProfile,
    SponsorshipProgressStatus,
)


class TestSponsorshipImportExport:
    def test_import_sponsorship_does_not_trigger_email(self, admin_user):
        dataset = Dataset()
        dataset.headers = [
            "id",
            "organization_name",
            "sponsor_contact_name",
            "sponsors_contact_email",
            "sponsorship_tier",
            "progress_status",
            "sponsorship_override_amount",
            "main_contact_user",
        ]
        dataset.append(
            [
                "",
                "Test 1",
                "",
                "",
                "",
                SponsorshipProgressStatus.AWAITING_RESPONSE.value,
                "",
                str(admin_user.id),
            ]
        )

        dataset.append(
            [
                "",
                "Test 2",
                "",
                "",
                "",
                SponsorshipProgressStatus.PAID.value,
                "",
                str(admin_user.id),
            ]
        )

        resource = SponsorshipProfileResource()
        mail.outbox.clear()
        resource.import_data(dataset, dry_run=False)
        assert len(mail.outbox) == 0  # no email
        resource.import_data(dataset, dry_run=True)
        assert len(mail.outbox) == 0  # no email

    def test_import_assigns_active_conference(self, admin_user, conference):
        dataset = Dataset()
        dataset.headers = ["id", "organization_name", "main_contact_user"]
        dataset.append(["", "Conf Co", str(admin_user.id)])
        SponsorshipProfileResource().import_data(dataset, dry_run=False)
        profile = SponsorshipProfile.objects.get(organization_name="Conf Co")
        assert profile.conference == conference

    def test_import_respects_explicit_conference_year(self, admin_user, conference):
        past = Conference.objects.create(
            year=2024, name="PyLadiesCon 2024", slug="2024"
        )
        dataset = Dataset()
        dataset.headers = ["id", "organization_name", "conference", "main_contact_user"]
        dataset.append(["", "Past Co", "2024", str(admin_user.id)])
        SponsorshipProfileResource().import_data(dataset, dry_run=False)
        profile = SponsorshipProfile.objects.get(organization_name="Past Co")
        assert profile.conference == past

    def test_export_includes_conference_year(self, conference):
        SponsorshipProfile.objects.create(
            organization_name="Exp Co", conference=conference
        )
        dataset = SponsorshipProfileResource().export()
        assert "conference" in dataset.headers
        idx = dataset.headers.index("conference")
        assert str(conference.year) in [str(row[idx]) for row in dataset]
