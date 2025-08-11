from django.contrib.auth.models import User
from django.db import models


class SponsorshipProfile(models.Model):
    SPONSORSHIP_TYPES = [
        ("Champion", "Champion"),
        ("Supporter", "Supporter"),
        ("Connector", "Connector"),
        ("Booster", "Booster"),
        ("Partner", "Partner"),
        ("Individual", "Individual"),
    ]

    APPLICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ("not_paid", "Not Paid"),
        ("paid", "Paid"),
        ("awaiting", "Awaiting Payment"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="sponsorship_user"
    )
    main_contact_user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="main_contact"
    )
    additional_contacts = models.ManyToManyField(
        User, blank=True, related_name="additional_contacts"
    )
    organization_name = models.CharField(max_length=255)
    sponsorship_type = models.CharField(max_length=20, choices=SPONSORSHIP_TYPES)
    # sponsorship_tier = models.ForeignKey("SponsorshipTier", on_delete=models.SET_NULL, null=True, blank = True)
    logo = models.ImageField(upload_to="sponsor_logos/", null=True, blank=True)
    amount_to_pay = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, null=True, blank=True
    )
    company_description = models.TextField()
    application_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="not_paid",
    )

    def __str__(self):
        return self.organization_name


# class SponsorshipTier(models.Model):
# amount = models.DecimalField(max_digits=10, decimal_places=2)
# name = models.CharField(max_length=100)
# description = models.TextField()

# def __str__(self):
# return self.name
