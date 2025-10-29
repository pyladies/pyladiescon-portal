# Markdown Email Templates

This document explains how to use the new Markdown-based email template system in PyLadiesCon Portal.

## Overview

PyLadiesCon Portal now supports **Markdown email templates** as an alternative to separate HTML and text templates. This system:

- ✅ **Simplifies email development** - Write once in Markdown, get both HTML and text versions
- ✅ **Improves maintainability** - Single source of truth for email content
- ✅ **Provides better formatting** - Rich Markdown features for better-looking emails
- ✅ **Maintains backward compatibility** - Existing HTML/text templates continue to work
- ✅ **Ensures security** - Automatic HTML sanitization prevents XSS attacks

## Quick Start

### Creating a Markdown Email Template

1. Create a `.md` file in the `templates/emails/` directory
2. Use Django template syntax combined with Markdown formatting
3. Call the email function with the `markdown_template` parameter

**Example template** (`templates/emails/welcome.md`):

```markdown
{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

# Welcome to PyLadiesCon, {{ user.first_name }}!

Thank you for joining our community. We're excited to have you on board.


**Welcome aboard!**

{% endblock content %}
```

### Sending the Email

```python
from common.send_emails import send_email

send_email(
    subject="Welcome to PyLadiesCon!",
    recipient_list=["user@example.com"],
    markdown_template="emails/welcome.md",
    context={"user": user_instance},
)
```

## Markdown Features Supported

### Headers

```markdown
# H1 Header
## H2 Header  
### H3 Header
```

### Text Formatting

```markdown
**Bold text**
*Italic text*
~~Strikethrough~~
`Code text`
```

### Links

```markdown
[Link text](https://example.com)
[Link with title](https://example.com "Link title")
```

### Lists

```markdown
## Unordered List
- Item 1
- Item 2
- Item 3

## Ordered List
1. First item
2. Second item
3. Third item
```

### Code Blocks

```markdown
```python
def hello_world():
    print("Hello, PyLadiesCon!")
```
```

### Blockquotes

```markdown
> This is a blockquote
> with multiple lines
```

### Horizontal Rules

```markdown
---
```

### Tables (GitHub Flavored Markdown)

```markdown
| Feature | Status |
|---------|--------|
| Markdown | ✅ Working |
| HTML | ✅ Working |
| Text | ✅ Working |
```

## Django Template Integration

Markdown templates work seamlessly with Django template features:

### Template Inheritance

```markdown
{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
# Your content here
{% endblock content %}
```

### Template Tags and Filters

```markdown
# Welcome {{ user.first_name|title }}!

{% if user.is_staff %}
As a staff member, you have special privileges.
{% endif %}

Your registration date: {{ user.date_joined|date:"F j, Y" }}

## Available Teams
{% for team in teams %}
- **{{ team.name }}** - {{ team.description }}
{% endfor %}
```

### Internationalization

```markdown
{% load i18n %}
# {% trans "Welcome to PyLadiesCon" %}

{% blocktrans with name=user.first_name %}
Hello {{ name }}, thank you for joining us!
{% endblocktrans %}
```

## Template Structure

### Base Template

All email templates should extend the base template for consistency:

```markdown
{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
# Your email content here
{% endblock content %}
```

### Template Locations

- **Base template**: `templates/emails/base_email.md`
- **Volunteer emails**: `templates/emails/volunteer/*.md`
- **Sponsorship emails**: `templates/emails/sponsorship/*.md`
- **Custom emails**: `templates/emails/your-app/*.md`

## API Reference

### send_email() Function

The updated `send_email()` function supports both legacy and Markdown templates:

```python
def send_email(
    subject: str,
    recipient_list: list,
    *,
    html_template: Optional[str] = None,      # Legacy HTML template
    text_template: Optional[str] = None,      # Legacy text template  
    markdown_template: Optional[str] = None,  # New Markdown template
    context: Optional[Dict[str, Any]] = None,
) -> None
```

**Parameters:**

- `subject`: Email subject line
- `recipient_list`: List of recipient email addresses
- `markdown_template`: Path to Markdown template (preferred for new emails)
- `html_template`: Path to HTML template (legacy support)
- `text_template`: Path to text template (legacy support)
- `context`: Dictionary of template variables

**Examples:**

```python
# New Markdown approach (recommended)
send_email(
    subject="Welcome!",
    recipient_list=["user@example.com"],
    markdown_template="emails/welcome.md",
    context={"user": user},
)

# Legacy approach (still supported)
send_email(
    subject="Welcome!",
    recipient_list=["user@example.com"],
    html_template="emails/welcome.html",
    text_template="emails/welcome.txt", 
    context={"user": user},
)
```

### send_markdown_email() Function

For direct Markdown email sending:

```python
from common.markdown_emails import send_markdown_email

send_markdown_email(
    subject="Test Email",
    recipient_list=["test@example.com"],
    markdown_template="emails/test.md",
    context={"name": "John"},
)
```

## Migration Guide

### Converting Existing Templates

To convert existing HTML/text email templates to Markdown:

1. **Create a new `.md` file** in the same directory
2. **Convert HTML to Markdown syntax**:
   - `<h1>Title</h1>` → `# Title`
   - `<strong>Bold</strong>` → `**Bold**`
   - `<a href="url">Link</a>` → `[Link](url)`
   - `<ul><li>Item</li></ul>` → `- Item`
3. **Update email sending code** to use `markdown_template` parameter
4. **Test thoroughly** to ensure formatting is correct

**Before (HTML template):**
```html
{% extends "emails/base_email.html" %}
{% block content %}
<h1>Welcome {{ user.first_name }}!</h1>
<p>Thank you for joining <strong>PyLadiesCon</strong>.</p>
<ul>
    <li>Join our <a href="https://discord.com/invite/example">Discord</a></li>
    <li>Read the <a href="https://conference.pyladies.com/docs/">docs</a></li>
</ul>
{% endblock content %}
```

**After (Markdown template):**
```markdown
{% extends "emails/base_email.md" %}
{% block content %}
# Welcome {{ user.first_name }}!

Thank you for joining **PyLadiesCon**.

- Join our [Discord](https://discord.com/invite/example)
- Read the [docs](https://conference.pyladies.com/docs/)
{% endblock content %}
```

### Gradual Migration Strategy

1. **Keep existing templates** working during transition
2. **Convert high-priority emails first** (welcome, onboarding)
3. **Test Markdown emails thoroughly** in development
4. **Update email sending calls** one at a time
5. **Remove old templates** after successful migration

## Best Practices

### 📝 Writing Guidelines

- **Use semantic headings** (`#`, `##`, `###`) for structure
- **Bold important information** with `**text**`
- **Create clear action items** with bullet points
- **Include descriptive link text** instead of raw URLs
- **Use horizontal rules** (`---`) to separate sections

### 🎨 Design Considerations

- **Keep line length reasonable** (under 80 characters when possible)
- **Use whitespace effectively** for readability
- **Group related information** under headings
- **Make calls-to-action prominent** with bold text or buttons

### 🔒 Security

- **HTML is automatically sanitized** to prevent XSS attacks
- **Only safe HTML tags are allowed** in the output
- **Link URLs are validated** and dangerous protocols are blocked
- **Template context is escaped** following Django security practices

### 🧪 Testing

```python
# Test Markdown email in development
from django.test import TestCase
from common.markdown_emails import send_markdown_email
from django.core import mail

class EmailTest(TestCase):
    def test_welcome_email(self):
        mail.outbox = []
        
        send_markdown_email(
            subject="Welcome Test",
            recipient_list=["test@example.com"],
            markdown_template="emails/welcome.md",
            context={"user": {"first_name": "Test"}},
        )
        
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("Welcome Test!", email.body)
        self.assertIn("<h1>Welcome Test!</h1>", email.alternatives[0][0])
```

## Troubleshooting

### Common Issues

**Template not found error:**
```
TemplateDoesNotExist: emails/my_template.md
```
- Check the template path is correct
- Ensure the file exists in `templates/emails/`
- Verify template inheritance paths

**Markdown not rendering:**
```python
# Make sure you're using markdown_template, not html_template
send_email(
    subject="Test",
    recipient_list=["test@example.com"],
    markdown_template="emails/test.md",  # ← Correct parameter
    context=context,
)
```

**Missing dependencies:**
```
ImportError: No module named 'markdown'
```
- Ensure `markdown` and `bleach` are installed
- Check `requirements-app.txt` includes the dependencies

### Debug Mode

Enable email debugging to see both HTML and text output:

```python
# In development settings
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

## Examples

### Volunteer Onboarding Email

```markdown
{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

# Welcome to the PyLadiesCon team, {{ profile.user.first_name }}!

Thank you for applying to volunteer with PyLadiesCon. We're excited to share that your application has been **approved**.

## 🎉 Team Assignment

You have been assigned to the following team(s):

{% for team in profile.teams.all %}
- **{{ team.short_name }}** - Team Lead(s): {% for lead in team.team_leads.all %}{{ lead.user.get_full_name }}{% if not forloop.last %}, {% endif %}{% endfor %}
{% endfor %}

## 📋 Action Items

**Please complete these steps within 7 days:**

- **Join our [Discord server](https://discord.com/invite/example)** *(Required)*
- **Read the [Volunteer Guide](https://conference.pyladies.com/docs/)**
- **Complete your [profile setup](https://{{ current_site.domain }}{% url 'volunteer:index' %})**

---

**Questions?** Reach out to your team lead or contact us on Discord.

**Thank you for volunteering!** 🙏

{% endblock content %}
```

### Sponsorship Notification Email

```markdown
{% extends "emails/base_email.md" %}
{% block content %}

# New Sponsorship Application 📋

Hello {{ recipient_name }}, a new sponsorship application has been submitted.

## Sponsor Details

- **Organization:** {{ profile.organization_name }}
- **Tier:** {{ profile.sponsorship_tier }}
- **Contact:** {{ profile.sponsor_contact_name }} ({{ profile.sponsors_contact_email }})
- **Amount:** ${{ profile.sponsorship_tier.amount }}

## Next Steps

Please review the application in the [admin dashboard](https://{{ current_site.domain }}/admin/).

{% endblock content %}
```

## Contributing

When contributing new email templates:

1. **Use Markdown format** for new templates (`.md` files)
2. **Follow the style guide** in this documentation  
3. **Include comprehensive tests** for email functionality
4. **Update this documentation** if adding new features
5. **Test in multiple email clients** when possible

---

*For technical questions about the Markdown email system, check the code in `common/markdown_emails.py` or reach out to the development team.*