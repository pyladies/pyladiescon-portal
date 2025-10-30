# Import the Markdown email system
from .markdown_emails import send_markdown_email


def send_email(
    subject,
    recipient_list,
    *,
    markdown_template,
    context=None,
):
    """Send an email using a Markdown template.

    This function only supports Markdown templates going forward.
    All email templates should be written in Markdown format.

    Args:
        subject: Email subject line
        recipient_list: List of recipient email addresses
        markdown_template: Path to Markdown template (required)
        context: Template context dictionary
    """
    return send_markdown_email(
        subject,
        recipient_list,
        markdown_template=markdown_template,
        context=context,
    )
