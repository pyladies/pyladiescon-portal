from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from common.send_emails import send_email
from volunteer.models import RoleTypes, VolunteerProfile
from .models import SponsorshipProfile

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_email_task(self, subject, markdown_template, context):
    """
    Send internal notification emails to team members.

    This task looks up admin/staff users and sends individual emails
    to each recipient for privacy.
    """
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
        return f"No recipients found for: {subject}"

    sent_count = 0
    # Send each email individually to each recipient, for privacy reasons
    for recipient in recipients:
        context["recipient_name"] = recipient.get_full_name() or recipient.username

        send_email(
            subject,
            [recipient.email],
            markdown_template=markdown_template,
            context=context,
        )
        sent_count += 1

    return f"Sent {sent_count} internal emails: {subject}"
    
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_sponsor_onboarding_email_task(self, profile_id):
    """
    Send onboarding notification to internal team when new sponsor is created.
    """
    
    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)
        
        context = {"profile": profile}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsorship Tracking: {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_onboarding.md"

        return send_internal_email_task(subject, markdown_template, context)
    
    except SponsorshipProfile.DoesNotExist:
        return f"SponsorshipProfile with id {profile_id} not found"
    
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_sponsor_progress_update_email_task(self, profile_id):
    """
    Send progress update notification to internal team.
    """
    
    try:
        profile = SponsorshipProfile.objects.get(id=profile_id)
        
        context = {"profile": profile}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Update in Sponsorship Tracking for {profile.organization_name}"
        markdown_template = "emails/sponsorship/internal_sponsor_updated.md"

        return send_internal_email_task(subject, markdown_template, context)
    
    except SponsorshipProfile.DoesNotExist:
        return f"SponsorshipProfile with id {profile_id} not found"
