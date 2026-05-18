from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from common.send_emails import send_email
from volunteer.constants import RoleTypes
from volunteer.models import VolunteerProfile

from .models import SponsorshipProfile

@receiver(post_save, sender=SponsorshipProfile)
def sponsorship_profile_signal(sender, instance, created, **kwargs):
    """Send emails when sponsorship profile is created or updated.
    Do not send emails if the instance was created via import/export. (too noisy).
    """
    if hasattr(instance, "from_import_export"):
        return
    from sponsorship.tasks import (
        send_internal_sponsor_onboarding_email_task,
        send_internal_sponsor_progress_update_email_task
    )
    if created:
        send_internal_sponsor_onboarding_email_task.delay(instance.id)
    else:
        send_internal_sponsor_progress_update_email_task.delay(instance.id)
    
