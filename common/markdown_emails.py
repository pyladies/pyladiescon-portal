"""Markdown-based email template system.

This module provides utilities for processing Markdown email templates,
converting them to both HTML and plain text formats for email delivery.
"""

import re
from typing import Dict, Any, Optional

import bleach
import markdown
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.template.loader import get_template


class MarkdownEmailRenderer:
    """Renders Markdown email templates to HTML and plain text."""
    
    # Allowed HTML tags for bleach sanitization
    ALLOWED_TAGS = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'a', 'img', 'table', 'thead',
        'tbody', 'tr', 'th', 'td', 'div', 'span', 'hr'
    ]
    
    # Allowed HTML attributes
    ALLOWED_ATTRIBUTES = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'width', 'height'],
        'div': ['class'],
        'span': ['class'],
        'th': ['scope'],
        'td': ['colspan', 'rowspan'],
    }
    
    def __init__(self):
        """Initialize the Markdown processor with extensions."""
        self.md = markdown.Markdown(
            extensions=[
                'markdown.extensions.extra',
                'markdown.extensions.nl2br',
                'markdown.extensions.sane_lists',
            ],
            extension_configs={
                'markdown.extensions.extra': {},
            }
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
            html,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            strip=True
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
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize line breaks
        text = re.sub(r'[ \t]+', ' ', text)      # Normalize spaces
        
        return text.strip()


def send_markdown_email(
    subject: str,
    recipient_list: list,
    *,
    markdown_template: Optional[str] = None,
    text_template: Optional[str] = None,
    html_template: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Send an email using Markdown, text, or HTML templates.
    
    This function supports three modes:
    1. Markdown template: Converts to both HTML and text
    2. Legacy mode: Uses separate HTML and text templates
    3. Text only: Uses text template only
    
    Args:
        subject: Email subject line
        recipient_list: List of recipient email addresses
        markdown_template: Path to Markdown template (preferred)
        text_template: Path to text template (legacy)
        html_template: Path to HTML template (legacy)
        context: Template context dictionary
    """
    context = context or {}
    context["current_site"] = Site.objects.get_current()
    
    renderer = MarkdownEmailRenderer()
    
    if markdown_template:
        # New Markdown-based approach
        markdown_content = renderer.render_template(markdown_template, context)
        html_content = renderer.markdown_to_html(markdown_content)
        text_content = renderer.markdown_to_text(markdown_content)
        
    elif html_template and text_template:
        # Legacy approach with separate HTML and text templates
        from django.template.loader import render_to_string
        html_content = render_to_string(html_template, context=context)
        text_content = render_to_string(text_template, context=context)
        
    elif text_template:
        # Text-only approach
        from django.template.loader import render_to_string
        text_content = render_to_string(text_template, context=context)
        html_content = None
        
    else:
        raise ValueError(
            "Must provide either markdown_template, or text_template, "
            "or both html_template and text_template"
        )
    
    # Create and send the email
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    
    if html_content:
        msg.attach_alternative(html_content, "text/html")
    
    msg.send()


# Backward compatibility alias
send_email_markdown = send_markdown_email