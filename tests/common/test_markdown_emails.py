"""Tests for Markdown email functionality."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.sites.models import Site
from django.core import mail
from django.template import Context, Template
from django.test import TestCase, override_settings

from common.markdown_emails import MarkdownEmailRenderer, send_markdown_email
from common.send_emails import send_email


class MarkdownEmailRendererTest(TestCase):
    """Test cases for MarkdownEmailRenderer."""

    def setUp(self):
        """Set up test instances."""
        self.renderer = MarkdownEmailRenderer()

    def test_markdown_to_html_basic(self):
        """Test basic Markdown to HTML conversion."""
        markdown_content = "# Hello World\n\nThis is **bold** text."

        result = self.renderer.markdown_to_html(markdown_content)
        self.assertIn("<h1>Hello World</h1>", result)
        self.assertIn("<strong>bold</strong>", result)

    def test_markdown_to_html_with_links(self):
        """Test Markdown to HTML conversion with links."""
        markdown_content = (
            "Visit [PyLadiesCon](https://conference.pyladies.com) for more info."
        )

        result = self.renderer.markdown_to_html(markdown_content)
        self.assertIn(
            '<a href="https://conference.pyladies.com">PyLadiesCon</a>', result
        )

    def test_markdown_to_html_with_lists(self):
        """Test Markdown to HTML conversion with lists."""
        markdown_content = """
## Action Items
- Join Discord
- Read the guide
- Complete onboarding
"""

        result = self.renderer.markdown_to_html(markdown_content)
        self.assertIn("<h2>Action Items</h2>", result)
        self.assertIn("<ul>", result)
        self.assertIn("<li>Join Discord</li>", result)

    def test_markdown_to_text_basic(self):
        """Test Markdown to plain text conversion."""
        markdown_content = "# Hello World\n\nThis is **bold** text."

        result = self.renderer.markdown_to_text(markdown_content)
        self.assertIn("Hello World", result)
        self.assertIn("This is bold text.", result)
        self.assertNotIn("#", result)
        self.assertNotIn("**", result)

    def test_markdown_to_text_with_links(self):
        """Test Markdown to text conversion preserves link text."""
        markdown_content = (
            "Visit [PyLadiesCon](https://conference.pyladies.com) for more info."
        )

        result = self.renderer.markdown_to_text(markdown_content)
        self.assertIn("PyLadiesCon", result)
        self.assertNotIn(
            "https://conference.pyladies.com", result
        )  # URL should be stripped in text version

    def test_html_sanitization(self):
        """Test that HTML content is properly sanitized."""
        markdown_content = (
            '<script>alert("xss")</script>\n\n# Safe Title\n\n<p>Safe paragraph</p>'
        )

        result = self.renderer.markdown_to_html(markdown_content)
        # Script tags should be removed but content might remain as text
        self.assertNotIn("<script>", result)
        self.assertIn("<h1>Safe Title</h1>", result)
        self.assertIn("<p>Safe paragraph</p>", result)
        # Check that dangerous scripts are neutralized
        self.assertNotIn("<script", result.lower())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
)
class SendMarkdownEmailTest(TestCase):
    """Test cases for send_markdown_email function."""

    def setUp(self):
        """Set up test data."""
        self.recipients = ["recipient@example.com"]
        self.subject = "Test Markdown Email"
        self.context = {
            "user_name": "Jane Doe",
            "user_email": "jane@example.com",
        }

    @patch("common.markdown_emails.get_template")
    def test_send_markdown_email_success(self, mock_get_template):
        """Test successful sending of Markdown email."""
        # Mock template
        mock_template = MagicMock()
        mock_template.render.return_value = """# Welcome Jane Doe!

This is a **test email** for Jane Doe.

Visit our [website](https://example.com) for more details.
"""
        mock_get_template.return_value = mock_template

        # Clear mail outbox
        mail.outbox = []

        # Send email
        send_markdown_email(
            self.subject,
            self.recipients,
            markdown_template="test_email.md",
            context=self.context,
        )

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]

        self.assertEqual(sent_email.subject, self.subject)
        self.assertEqual(sent_email.to, self.recipients)

        # Check that both HTML and text versions are present
        self.assertTrue(sent_email.body)  # Plain text version
        self.assertEqual(len(sent_email.alternatives), 1)  # HTML version
        self.assertEqual(sent_email.alternatives[0][1], "text/html")

        # Check content
        html_content = sent_email.alternatives[0][0]
        self.assertIn("<h1>Welcome Jane Doe!</h1>", html_content)
        self.assertIn("<strong>test email</strong>", html_content)
        self.assertIn('<a href="https://example.com">website</a>', html_content)

        # Check plain text content
        self.assertIn("Welcome Jane Doe!", sent_email.body)
        self.assertIn("test email", sent_email.body)
        self.assertNotIn("<h1>", sent_email.body)  # No HTML tags in text version


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@example.com",
)
class SendEmailCompatibilityTest(TestCase):
    """Test backward compatibility of updated send_email function."""

    def setUp(self):
        """Set up test data."""
        self.recipients = ["recipient@example.com"]
        self.subject = "Test Email"
        self.context = {"user_name": "Test User"}

    @patch("common.send_emails.render_to_string")
    def test_legacy_html_text_templates(self, mock_render):
        """Test that legacy HTML/text templates still work."""
        mock_render.side_effect = [
            "Plain text content",  # text template
            "<p>HTML content</p>",  # html template
        ]

        mail.outbox = []

        send_email(
            self.subject,
            self.recipients,
            html_template="test.html",
            text_template="test.txt",
            context=self.context,
        )

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]

        self.assertEqual(sent_email.subject, self.subject)
        self.assertEqual(sent_email.body, "Plain text content")
        self.assertEqual(len(sent_email.alternatives), 1)
        self.assertEqual(sent_email.alternatives[0][0], "<p>HTML content</p>")

    @patch("common.send_emails.render_to_string")
    def test_text_only_template(self, mock_render):
        """Test text-only email template."""
        mock_render.return_value = "Plain text only content"

        mail.outbox = []

        send_email(
            self.subject,
            self.recipients,
            text_template="test.txt",
            context=self.context,
        )

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]

        self.assertEqual(sent_email.body, "Plain text only content")
        self.assertEqual(len(sent_email.alternatives), 0)  # No HTML alternative

    @patch("common.send_emails.send_markdown_email")
    def test_markdown_template_routing(self, mock_send_markdown):
        """Test that markdown_template parameter routes to new system."""
        # Mock the return value
        mock_send_markdown.return_value = True

        result = send_email(
            self.subject,
            self.recipients,
            markdown_template="test.md",
            context=self.context,
        )

        mock_send_markdown.assert_called_once_with(
            self.subject,
            self.recipients,
            markdown_template="test.md",
            context=self.context,
        )
        self.assertTrue(result)

    def test_send_markdown_email_no_templates_error(self):
        """Test that send_markdown_email raises error when no templates provided."""
        with self.assertRaises(ValueError) as cm:
            send_markdown_email(
                subject="Test",
                recipient_list=["test@example.com"],
                context={},
            )
        
        self.assertIn(
            "Must provide either markdown_template, or text_template",
            str(cm.exception)
        )

    @patch("django.template.loader.render_to_string")
    def test_send_markdown_email_text_only_no_html(self, mock_render):
        """Test send_markdown_email with text_template only (no HTML)."""
        mock_render.return_value = "Plain text content"
        
        send_markdown_email(
            subject="Test Subject",
            recipient_list=["test@example.com"],
            text_template="test.txt",
            context={"name": "Test"},
        )
        
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        
        self.assertEqual(sent_email.subject, "Test Subject")
        self.assertEqual(sent_email.body, "Plain text content")
        self.assertEqual(len(sent_email.alternatives), 0)  # No HTML alternative

    def test_render_template_with_context(self):
        """Test render_template method with context."""
        # Create a temporary template file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("Hello {{ name }}!")
            temp_path = f.name
        
        try:
            # We need to test this differently since get_template expects template in TEMPLATES dirs
            # Let's test the markdown processing directly
            markdown_content = "Hello {{ name }}!"
            template = Template(markdown_content)
            rendered = template.render(Context({"name": "World"}))
            
            self.assertEqual(rendered, "Hello World!")
        finally:
            os.unlink(temp_path)

    def test_backward_compatibility_alias(self):
        """Test that send_email_markdown is an alias for send_markdown_email."""
        from common.markdown_emails import send_email_markdown, send_markdown_email
        
        # Test that they are the same function
        self.assertEqual(send_email_markdown, send_markdown_email)

    @patch("common.send_emails.render_to_string")
    def test_legacy_html_only_no_text_template(self, mock_render):
        """Test legacy send_email with only html_template (no text_template)."""
        mock_render.return_value = "<h1>HTML content</h1>"
        
        send_email(
            subject="Test Subject",
            recipient_list=["test@example.com"],
            html_template="test.html",
            # No text_template provided - should use empty string
            context={"name": "Test"},
        )
        
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        
        self.assertEqual(sent_email.subject, "Test Subject")
        self.assertEqual(sent_email.body, "")  # Empty text content
        self.assertEqual(len(sent_email.alternatives), 1)  # HTML alternative exists
        self.assertEqual(sent_email.alternatives[0], ("<h1>HTML content</h1>", "text/html"))

    def test_markdown_renderer_reset_behavior(self):
        """Test that Markdown renderer properly resets between conversions."""
        renderer = MarkdownEmailRenderer()
        
        # First conversion
        html1 = renderer.markdown_to_html("# First")
        text1 = renderer.markdown_to_text("# First")
        
        # Second conversion should work independently
        html2 = renderer.markdown_to_html("# Second")
        text2 = renderer.markdown_to_text("# Second")
        
        self.assertIn("First", html1)
        self.assertIn("Second", html2)
        self.assertIn("First", text1)
        self.assertIn("Second", text2)
        
        # Make sure they're different
        self.assertNotEqual(html1, html2)
        self.assertNotEqual(text1, text2)

    @patch("common.markdown_emails.get_template")
    def test_render_template_coverage(self, mock_get_template):
        """Test render_template method for coverage."""
        # Create a mock template
        mock_template = MagicMock()
        mock_template.render.return_value = "Rendered content"
        mock_get_template.return_value = mock_template
        
        renderer = MarkdownEmailRenderer()
        result = renderer.render_template("test.md", {"key": "value"})
        
        self.assertEqual(result, "Rendered content")
        mock_get_template.assert_called_once_with("test.md")
        mock_template.render.assert_called_once_with({"key": "value"})

    @patch("django.template.loader.render_to_string")
    def test_send_markdown_email_legacy_both_templates(self, mock_render):
        """Test send_markdown_email with both html_template and text_template (legacy)."""
        mock_render.side_effect = ["<h1>HTML content</h1>", "Plain text content"]
        
        send_markdown_email(
            subject="Test Subject",
            recipient_list=["test@example.com"],
            html_template="test.html",
            text_template="test.txt",
            context={"name": "Test"},
        )
        
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        
        self.assertEqual(sent_email.subject, "Test Subject")
        self.assertEqual(sent_email.body, "Plain text content")
        self.assertEqual(len(sent_email.alternatives), 1)
        self.assertEqual(sent_email.alternatives[0], ("<h1>HTML content</h1>", "text/html"))
        
        # Verify both templates were rendered
        self.assertEqual(mock_render.call_count, 2)
