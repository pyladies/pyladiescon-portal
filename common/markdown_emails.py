"""Markdown-based email template system.

This module provides utilities for processing Markdown email templates,
converting them to both HTML and plain text formats for email delivery.
"""

import re
from typing import Any, Dict, Optional, Tuple

import bleach
import markdown
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template


class MarkdownEmailRenderer:
    """Renders Markdown email templates to HTML and plain text."""

    # Allowed HTML tags for bleach sanitization
    ALLOWED_TAGS = [
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "blockquote",
        "pre",
        "code",
        "a",
        "img",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "div",
        "span",
        "hr",
    ]

    # Allowed HTML attributes
    ALLOWED_ATTRIBUTES = {
        "a": ["href", "title"],
        "img": ["src", "alt", "width", "height"],
        "div": ["class"],
        "span": ["class"],
        "th": ["scope"],
        "td": ["colspan", "rowspan"],
    }

    def __init__(self):
        """Initialize the Markdown processor with extensions."""
        self.md = markdown.Markdown(
            extensions=[
                "markdown.extensions.extra",
                "markdown.extensions.nl2br",
                "markdown.extensions.sane_lists",
            ],
            extension_configs={
                "markdown.extensions.extra": {},
            },
        )

    def render_template(self, template_path: str, context: Dict[str, Any]) -> str:
        """Render a Markdown template with Django template context.

        Args:
            template_path: Path to the Markdown template file
            context: Template context dictionary

        Returns:
            Rendered Markdown content as string
        """
        template = get_template(template_path)
        return template.render(context)

    def markdown_to_html(self, markdown_content: str) -> str:
        """Convert Markdown content to sanitized HTML.

        Args:
            markdown_content: Raw Markdown content

        Returns:
            Sanitized HTML string
        """
        # Convert Markdown to HTML
        html = self.md.convert(markdown_content)

        # Reset the Markdown instance for next use
        self.md.reset()

        # Sanitize the HTML to prevent XSS
        clean_html = bleach.clean(
            html, tags=self.ALLOWED_TAGS, attributes=self.ALLOWED_ATTRIBUTES, strip=True
        )

        return clean_html

    def markdown_to_text(self, markdown_content: str) -> str:
        """Convert Markdown content to plain text.

        Args:
            markdown_content: Raw Markdown content

        Returns:
            Plain text string
        """
        # First convert to HTML, then strip HTML tags for clean text
        html = self.md.convert(markdown_content)
        self.md.reset()

        # Remove HTML tags and decode entities
        text = bleach.clean(html, tags=[], strip=True)

        # Clean up extra whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)  # Normalize line breaks
        text = re.sub(r"[ \t]+", " ", text)  # Normalize spaces

        return text.strip()


def render_markdown_email(
    markdown_template: str, context: Dict[str, Any]
) -> Tuple[str, str, str]:
    """Render the template once; return the Markdown, the HTML and the text.

    The Markdown is the source of both parts, which is why the sent-email
    record keeps it and nothing else.
    """
    context["current_site"] = Site.objects.get_current()
    renderer = MarkdownEmailRenderer()
    markdown_content = renderer.render_template(markdown_template, context)
    return (
        markdown_content,
        renderer.markdown_to_html(markdown_content),
        renderer.markdown_to_text(markdown_content),
    )


def deliver_markdown_email(
    subject: str, recipient_list: list, html_content: str, text_content: str
) -> None:
    """Hand the rendered parts to the mail backend.

    Replies go to the sender address (the conference's own), set explicitly
    so it holds whatever the backend or mail client would otherwise do. It
    adds no recipient: nobody is copied on what is sent, because some of
    it carries a personal sign-in link.
    """
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
        reply_to=[settings.DEFAULT_FROM_EMAIL],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_markdown_email(
    subject: str,
    recipient_list: list,
    *,
    markdown_template: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Send an email using a Markdown template, with no record kept.

    Converts the Markdown template to both HTML and plain text versions
    for optimal email client compatibility. ``common.send_emails.send_email``
    is the door the portal's own mail goes through, because it records.

    Args:
        subject: Email subject line
        recipient_list: List of recipient email addresses
        markdown_template: Path to Markdown template (required)
        context: Template context dictionary
    """
    _, html_content, text_content = render_markdown_email(
        markdown_template, context or {}
    )
    deliver_markdown_email(subject, recipient_list, html_content, text_content)


# Backward compatibility alias
send_email_markdown = send_markdown_email
