print("✅ sponsorship.signals loaded")

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string

from .models import SponsorshipProfile


def _send_email(
    subject, recipient_list, *, html_template=None, text_template=None, context=None
):
    context = context or {}
    context["current_site"] = Site.objects.get_current()

    text_content = render_to_string(text_template, context)
    html_content = render_to_string(html_template, context)

    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


@receiver(post_save, sender=SponsorshipProfile)
def sponsorship_profile_signal(sender, instance, created, **kwargs):
    """Send emails when sponsorship profile is submitted or approved."""
    if created:
        # Email on submission
        subject = (
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Sponsorship Application Received"
        )
        _send_email(
            subject,
            [instance.user.email],
            html_template="sponsorship/email/sponsor_status_update.html",
            text_template="sponsorship/email/sponsor_status_update.txt",
            context={"profile": instance},
        )
    elif instance.application_status == "approved":
        # Email on approval
        subject = (
            f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Sponsorship Profile Approved"
        )
        _send_email(
            subject,
            [instance.user.email],
            html_template="sponsorship/email/sponsor_approved.html",
            text_template="sponsorship/email/sponsor_approved.txt",
            context={"profile": instance},
        )

        # Internal team notification
        internal_subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsorship Approved: {instance.organization_name}"
        _send_email(
            internal_subject,
            ["team@example.com"],  # Replace with real internal emails later
            html_template="sponsorship/email/team_status_notification.html",
            text_template="sponsorship/email/team_status_notification.txt",
            context={"profile": instance},
        )
