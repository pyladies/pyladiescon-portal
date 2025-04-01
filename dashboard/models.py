from django.db import models

#code models for various dashboard implementations

class SponsorshipApplication(models.Model):
    STATUS_CHOICES = [("Pending", "Pending"), ("Approved", "Approved"), ("Rejected", "Rejected")]
    company_name = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")

class VolunteerTask(models.Model):
    STATUS_CHOICES = [("Pending", "Pending"), ("Completed", "Completed")]
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")

class StaffTask(models.Model):
    STATUS_CHOICES = [("Pending", "Pending"), ("Completed", "Completed")]
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
