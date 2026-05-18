from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from common.send_emails import send_email
from volunteer.constants import RoleTypes
from volunteer.models import VolunteerProfile


@shared_task(
    name='sponsorship.tasks.send_internal_sponsor_onboarding_email',
    bind=True,
    max_retries=3,
    default_retry_delay=60  # Retry after 60 seconds
)
def send_internal_sponsor_onboarding_email_task(self, profile_id):
    """
    Background task to send internal sponsor onboarding email.
    
    Args:
        profile_id: ID of the SponsorshipProfile instance
    """
    from sponsorship.models import SponsorshipProfile
    
    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)
        
        # Get recipients (same logic as before)
        recipients = User.objects.filter(
            Q(
                id__in=VolunteerProfile.objects.prefetch_related("roles")
                .filter(roles__short_name__in=[RoleTypes.ADMIN, RoleTypes.STAFF])
                .values_list("id", flat=True)
            )
            | Q(is_superuser=True)
            | Q(is_staff=True)
        ).distinct()
        
        if not recipients.exists():
            return f"No recipients found for profile {profile_id}"
        
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsorship Tracking: {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_onboarding.md"
        
        # Send emails to each recipient
        emails_sent = 0
        for recipient in recipients:
            context = {
                'profile': profile,
                'recipient_name': recipient.get_full_name() or recipient.username
            }
            
            send_email(
                subject,
                [recipient.email],
                markdown_template=markdown_template,
                context=context,
            )
            emails_sent += 1
        
        return f"Successfully sent {emails_sent} emails for sponsorship {profile.organization_name}"
        
    except SponsorshipProfile.DoesNotExist:
        # Don't retry if profile doesn't exist
        return f"SponsorshipProfile {profile_id} not found"
        
    except Exception as exc:
        # Retry on other exceptions
        raise self.retry(exc=exc)


@shared_task(
    name='sponsorship.tasks.send_internal_sponsor_progress_update_email',
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def send_internal_sponsor_progress_update_email_task(self, profile_id):
    """
    Background task to send internal sponsor progress update email.
    
    Args:
        profile_id: ID of the SponsorshipProfile instance
    """
    from sponsorship.models import SponsorshipProfile
    
    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)
        
        # Get recipients
        recipients = User.objects.filter(
            Q(
                id__in=VolunteerProfile.objects.prefetch_related("roles")
                .filter(roles__short_name__in=[RoleTypes.ADMIN, RoleTypes.STAFF])
                .values_list("id", flat=True)
            )
            | Q(is_superuser=True)
            | Q(is_staff=True)
        ).distinct()
        
        if not recipients.exists():
            return f"No recipients found for profile {profile_id}"
        
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Update in Sponsorship Tracking for {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_updated.md"
        
        emails_sent = 0
        for recipient in recipients:
            context = {
                'profile': profile,
                'recipient_name': recipient.get_full_name() or recipient.username
            }
            
            send_email(
                subject,
                [recipient.email],
                markdown_template=markdown_template,
                context=context,
            )
            emails_sent += 1
        
        return f"Successfully sent {emails_sent} update emails for sponsorship {profile.organization_name}"
        
    except SponsorshipProfile.DoesNotExist:
        return f"SponsorshipProfile {profile_id} not found"
        
    except Exception as exc:
        raise self.retry(exc=exc)