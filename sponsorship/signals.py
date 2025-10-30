from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from common.send_emails import send_email
from volunteer.models import RoleTypes, VolunteerProfile

from .models import SponsorshipProfile


def _send_internal_email(
    subject,
    *,
    markdown_template,
    context=None,
):
    """Helper function to send an internal email.

    Lookup who the internal team members who should receive the email and then send the emails individually.
    Send the email to staff, admin, and sponsorship team members

    Only supports Markdown templates going forward.
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
        return

    # send each email individually to each recipient, for privacy reasons
    for recipient in recipients:
        context["recipient_name"] = recipient.get_full_name() or recipient.username

        send_email(
            subject,
            [recipient.email],
            markdown_template=markdown_template,
            context=context,
        )


def send_internal_sponsor_onboarding_email(instance):
    """Send email to team whenever a new sponsor is created.

    Emails will be sent to team members with the role type Staff or Admin, and to sponsorship team.
    Emails will also be sent to users with is_superuser or is_staff set to True.
    """
    context = {"profile": instance}
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsorship Tracking: {instance.organization_name}"

    markdown_template = "emails/sponsorship/internal_sponsor_onboarding.md"

    _send_internal_email(
        subject,
        markdown_template=markdown_template,
        context=context,
    )


def send_internal_sponsor_progress_update_email(instance):
    """Send email to team whenever there is a change in sponsorship progress."""

    context = {"profile": instance}
    subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Update in Sponsorship Tracking for {instance.organization_name}"

    markdown_template = "emails/sponsorship/internal_sponsor_updated.md"

    _send_internal_email(
        subject,
        markdown_template=markdown_template,
        context=context,
    )


@receiver(post_save, sender=SponsorshipProfile)
def sponsorship_profile_signal(sender, instance, created, **kwargs):
    """Send emails when sponsorship profile is created or updated.
    Do not send emails if the instance was created via import/export. (too noisy).
    """
    if hasattr(instance, "from_import_export"):
        return
    else:
        if created:
            send_internal_sponsor_onboarding_email(instance)
        else:
            send_internal_sponsor_progress_update_email(instance)
