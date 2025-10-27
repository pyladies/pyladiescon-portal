from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_email(
    subject,
    recipient_list,
    *,
    html_template=None,
    text_template=None,
    context=None,
):
    """Helper function to send an email."""
    context = context or {}
    context["current_site"] = Site.objects.get_current()
    text_content = render_to_string(
        text_template,
        context=context,
    )
    html_content = render_to_string(
        html_template,
        context=context,
    )
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()
