from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .constants import ApplicationStatus
from .gdrive_utils import add_to_gdrive, remove_from_gdrive
from .models import VolunteerProfile


@receiver(pre_save, sender=VolunteerProfile)
def track_approval_status(sender, instance, **kwargs):
    """Capture previous status before save"""
    try:
        original = VolunteerProfile.objects.get(pk=instance.pk)
        instance._original_application_status = original.application_status
    except VolunteerProfile.DoesNotExist:
        instance._original_application_status = None


@receiver(post_save, sender=VolunteerProfile)
def handle_approval_status(sender, instance, **kwargs):
    """Handle GDrive access based on status changes"""
    original_status = instance._original_application_status
    new_status = instance.application_status

    email = instance.user.email

    if new_status == ApplicationStatus.APPROVED:
        # New approval or re-approval
        if original_status != ApplicationStatus.APPROVED and email:
            add_to_gdrive(email)
    else:
        # Revoked approval
        if original_status == ApplicationStatus.APPROVED and email:
            remove_from_gdrive(email)
