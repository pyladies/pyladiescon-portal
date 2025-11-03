from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_sponsorship_status_emails(profile):
    user = profile.user

    # Email to sponsor
    sponsor_subject = "Your Sponsorship Profile Has Been Approved"
    sponsor_message = render_to_string(
        "sponsorship/email/sponsor_status_update.txt",
        {"user": user, "profile": profile},
    )
    send_mail(
        sponsor_subject, sponsor_message, settings.DEFAULT_FROM_EMAIL, [user.email]
    )

    # Email to internal team (hardcoded for now)
    team_subject = f"New Sponsorship Approved: {profile.organization_name}"
    team_message = render_to_string(
        "sponsorship/email/team_status_notification.txt",
        {"user": user, "profile": profile},
    )
    send_mail(
        team_subject,
        team_message,
        settings.DEFAULT_FROM_EMAIL,
        ["team@example.com"],  # Replace with actual team emails later
    )


def send_psf_invoice_request_email(profile):
    """Send email to PSF accounting team requesting sponsorship contract preparation."""
    from common.markdown_emails import send_markdown_email

    subject = f"PyLadiesCon Sponsorship Contract Request: {profile.organization_name}"

    # TODO: Replace with actual PSF accounting email addresses
    psf_accounting_emails = ["accounting@python.org", "sponsors@pyladies.com"]

    send_markdown_email(
        subject=subject,
        recipient_list=psf_accounting_emails,
        markdown_template="sponsorship/email/psf_invoice_request.md",
        context={"profile": profile},
    )
