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
    
    SPOSNORSHIP_PRICES = {
        "Champion": 10000.00,
        "Supporter": 5000.00,
        "Connector": 2500.00,
        "Booster": 1000.00,
        "Partner": 500.00,
        "Individual": 100.00,
    }

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
    
    @classmethod
    def get_sponsorship_prices(cls):
        """Return the sponsorship pricing dictionary"""
        return cls.SPONSORSHIP_PRICING

    def get_default_amount(self):
        """Get the default amount for this sponsorship type"""
        return self.SPONSORSHIP_PRICING.get(self.sponsorship_type, 0.00)

    def save(self, *args, **kwargs):
        """Override save to auto-set amount if not provided"""
        if self.amount_to_pay is None or self.amount_to_pay == 0:
            self.amount_to_pay = self.get_default_amount()
        super().save(*args, **kwargs)

    @property
    def sponsorship_type_display_with_price(self):
        """Return sponsorship type with its default price for display"""
        price = self.SPONSORSHIP_PRICING.get(self.sponsorship_type, 0)
        return f"{self.get_sponsorship_type_display()} (${price:,.2f})"


# class SponsorshipTier(models.Model):
# amount = models.DecimalField(max_digits=10, decimal_places=2)
# name = models.CharField(max_length=100)
# description = models.TextField()

# def __str__(self):
# return self.name
