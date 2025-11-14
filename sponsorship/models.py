from django.contrib.auth.models import User
from django.db import models

from portal.models import BaseModel


class SponsorshipProgressStatus(models.IntegerChoices):
    """Sponsorship Progress status."""

    NOT_CONTACTED = 1, "Not Contacted"
    AWAITING_RESPONSE = 2, "Awaiting Response"
    REJECTED = 3, "Rejected"
    ACCEPTED = 4, "Accepted"
    APPROVED = 5, "Approved"
    AGREEMENT_SENT = 6, "Agreement Sent"
    AGREEMENT_SIGNED = 7, "Agreement Signed"
    INVOICED = 8, "Invoiced"
    PAID = 9, "Paid"
    CANCELLED = 10, "Cancelled"


class SponsorshipTier(BaseModel):
    name = models.CharField(max_length=100)  # "Championship", "Supporter", etc.
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # 10000.00, etc.
    description = models.TextField()

    def __str__(self):
        return f"{self.name} (${self.amount:.2f})"


class SponsorshipProfile(BaseModel):

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="sponsorship_user",
        null=True,
        blank=True,
    )
    main_contact_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="main_contact_user",
        null=True,
        blank=True,
    )
    additional_contacts = models.ManyToManyField(
        User, blank=True, related_name="additional_contacts"
    )
    organization_name = models.CharField(max_length=255)
    sponsorship_tier = models.ForeignKey(
        "SponsorshipTier", on_delete=models.SET_NULL, null=True, blank=True
    )
    logo = models.ImageField(upload_to="sponsor_logos/", null=True, blank=True)
    company_description = models.TextField(blank=True, null=True)
    progress_status = models.IntegerField(
        choices=SponsorshipProgressStatus,
        default=SponsorshipProgressStatus.NOT_CONTACTED,
    )
    sponsor_contact_name = models.CharField(max_length=255, blank=True, null=True)
    sponsors_contact_email = models.EmailField(blank=True, null=True)
    organization_address = models.TextField(blank=True, null=True)
    sponsorship_override_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    po_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Purchase Order number for the sponsorship contract and invoice",
    )

    def __str__(self):
        return self.organization_name


class IndividualDonation(BaseModel):
    """Representation of Individual Donations coming in from PSF CivicCRM platform."""

    transaction_id = models.CharField(max_length=100, unique=True)
    donor_name = models.CharField(
        max_length=255, null=True, blank=True
    )  # Optional, only needed if > 50$
    transaction_date = models.DateTimeField(null=True, blank=True)
    donation_amount = models.DecimalField(max_digits=10, decimal_places=2)
    donor_email = models.EmailField()  # required
    is_anonymous = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.transaction_id}: ${self.donation_amount:.2f}"
