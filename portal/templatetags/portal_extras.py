import bleach
import markdown as markdown_lib
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Tags/attributes allowed in rendered descriptions. Kept tight since the output
# is shown on public pages; everything else is stripped by bleach.
_MARKDOWN_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "code",
    "pre",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
]
_MARKDOWN_ATTRS = {"a": ["href", "title", "rel"]}


@register.filter
def markdownify(value):
    """Render Markdown to sanitized HTML for display."""
    if not value:
        return ""
    html = markdown_lib.markdown(value, extensions=["extra", "nl2br", "sane_lists"])
    clean = bleach.clean(html, tags=_MARKDOWN_TAGS, attributes=_MARKDOWN_ATTRS)
    return mark_safe(clean)


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get a value from a dictionary by key,
    returning None if not found.
    """
    return dictionary.get(key)


@register.filter
def as_currency(value):
    """
    Template filter to format a number as currency.
    """
    try:
        amount = float(value)
        return f"${amount:,.0f}"
    except (TypeError, ValueError):
        return ""
