#model schema creation for more functionality addition to sponsorship portal
from django.db import models

class SponsorshipApplication(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]
    company_name = models.CharField(max_length=255)
    email = models.EmailField()
    tier = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
    contract_sent = models.BooleanField(default=False)
    payment_received = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.company_name} - {self.status}"

class SponsorshipAsset(models.Model):
    sponsorship_application = models.ForeignKey(SponsorshipApplication, on_delete=models.CASCADE)
    asset_file = models.FileField(upload_to="sponsorship_assets/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Asset for {self.sponsorship_application.company_name}"
