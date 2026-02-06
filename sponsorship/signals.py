from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import SponsorshipProfile
from .tasks import (
    send_internal_sponsor_onboarding_email_task,
    send_internal_sponsor_progress_update_email_task,
)

@receiver(post_save, sender=SponsorshipProfile)
def sponsorship_profile_signal(sender, instance, created, **kwargs):
    """Send emails when sponsorship profile is created or updated.

    Emails are sent asynchronously using Celery tasks to avoid blocking
    the request/response cycle.

    Do not send emails if the instance was created via import/export. (too noisy).
    """
    if hasattr(instance, "from_import_export"):
        return
    
    if created:
        # Send onboarding email asynchronously
        send_internal_sponsor_onboarding_email_task.delay(instance.id)
    else:
        # Send progress update email asynchronously
        send_internal_sponsor_progress_update_email_task.delay(instance.id)
