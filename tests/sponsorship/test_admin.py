from django.core import mail
from tablib import Dataset

from sponsorship.admin import SponsorshipProfileResource
from sponsorship.models import (
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
