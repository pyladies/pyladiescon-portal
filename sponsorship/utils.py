from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string

from .models import SponsorshipProfile


def _send_email(
    subject, recipient_list, *, html_template=None, text_template=None, context=None
):
    context = context or {}
    context["current_site"] = Site.objects.get_current()
    text_content = render_to_string(text_template, context=context)
    html_content = render_to_string(html_template, context=context)

    msg = EmailMultiAlternatives(
        subject, text_content, settings.DEFAULT_FROM_EMAIL, recipient_list
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_sponsor_onboarding_email(instance):
    if instance.application_status == "approved":
        context = {"profile": instance}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} Welcome Sponsor!"
        _send_email(
            subject,
            [instance.user.email],
            html_template="sponsorship/email/sponsor_onboarding.html",
            text_template="sponsorship/email/sponsor_onboarding.txt",
            context=context,
        )


def send_internal_sponsor_onboarding_email(instance):
    if instance.application_status == "approved":
        context = {"profile": instance}
        subject = f"{settings.ACCOUNT_EMAIL_SUBJECT_PREFIX} New Sponsor Approved: {instance.organization_name}"

        # Notify internal team
        internal_team = User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True)
        ).distinct()
        for user in internal_team:
            context["recipient_name"] = user.get_full_name() or user.username
            _send_email(
                subject,
                [user.email],
                html_template="sponsorship/email/internal_sponsor_onboarding.html",
                text_template="sponsorship/email/internal_sponsor_onboarding.txt",
                context=context,
            )
