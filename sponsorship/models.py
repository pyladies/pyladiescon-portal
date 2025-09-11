from django.contrib.auth.models import User
from django.db import models


class SponsorshipTier(models.Model):
    name = models.CharField(max_length=100)  # "Championship", "Supporter", etc.
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # 10000.00, etc.
    description = models.TextField()

    def __str__(self):
        return self.name


class SponsorshipProfile(models.Model):
    APPLICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="sponsorship_user"
    )
    main_contact_user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="main_contact_user"
    )
    additional_contacts = models.ManyToManyField(
        User, blank=True, related_name="additional_contacts"
    )
    organization_name = models.CharField(max_length=255)
    sponsorship_tier = models.ForeignKey(
        "SponsorshipTier", on_delete=models.SET_NULL, null=True, blank=True
    )
    logo = models.ImageField(upload_to="sponsor_logos/", null=True, blank=True)
    company_description = models.TextField()
    application_status = models.CharField(
        max_length=20,
        choices=APPLICATION_STATUS_CHOICES,
        default="pending",
    )

    def __str__(self):
        return self.organization_name