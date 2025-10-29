from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# Import the new Markdown email system
from .markdown_emails import send_markdown_email


def send_email(
    subject,
    recipient_list,
    *,
    html_template=None,
    text_template=None,
    markdown_template=None,
    context=None,
):
    """Helper function to send an email.
    
    This function supports both the new Markdown template system and legacy HTML/text templates.
    
    Args:
        subject: Email subject line
        recipient_list: List of recipient email addresses
        html_template: Path to HTML template (legacy)
        text_template: Path to text template (legacy)
        markdown_template: Path to Markdown template (preferred)
        context: Template context dictionary
    """
    # Use the new Markdown email system if markdown_template is provided
    if markdown_template:
        return send_markdown_email(
            subject,
            recipient_list,
            markdown_template=markdown_template,
            context=context,
        )
    
    # Fall back to legacy system for backward compatibility
    context = context or {}
    context["current_site"] = Site.objects.get_current()
    
    if text_template:
        text_content = render_to_string(
            text_template,
            context=context,
        )
    else:
        text_content = ""
    
    if html_template:
        html_content = render_to_string(
            html_template,
            context=context,
        )
    else:
        html_content = None
    
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    
    if html_content:
        msg.attach_alternative(html_content, "text/html")
    
    msg.send()
