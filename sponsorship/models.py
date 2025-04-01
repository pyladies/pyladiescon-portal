from django.db import models
from django.contrib.auth.models import User

class SponsorshipTier(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name


class SponsorshipProfile(models.Model):
    INDIVIDUAL = 'individual'
    ORGANIZATION = 'organization'

    SPONSORSHIP_TYPE_CHOICES = [
        (INDIVIDUAL, 'Individual'),
        (ORGANIZATION, 'Organization/Company'),
    ]

    APPLICATION_PENDING = 'pending'
    APPLICATION_APPROVED = 'approved'
    APPLICATION_REJECTED = 'rejected'
    APPLICATION_CANCELLED = 'cancelled'

    APPLICATION_STATUS_CHOICES = [
        (APPLICATION_PENDING, 'Pending'),
        (APPLICATION_APPROVED, 'Approved'),
        (APPLICATION_REJECTED, 'Rejected'),
        (APPLICATION_CANCELLED, 'Cancelled'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='sponsorship_profile')
    main_contact = models.OneToOneField(User, on_delete=models.CASCADE, related_name='main_contact_for')
    additional_contacts = models.ManyToManyField(User, blank=True, related_name='additional_sponsorship_contacts')
    sponsor_organization_name = models.CharField(max_length=255)
    sponsorship_type = models.CharField(max_length=20, choices=SPONSORSHIP_TYPE_CHOICES)
    sponsorship_tier = models.ForeignKey(SponsorshipTier, on_delete=models.SET_NULL, null=True)
    logo = models.ImageField(upload_to='sponsor_logos/')
    company_description = models.TextField()
    application_status = models.CharField(max_length=20, choices=APPLICATION_STATUS_CHOICES, default=APPLICATION_PENDING)

    def __str__(self):
        return self.sponsor_organization_name
