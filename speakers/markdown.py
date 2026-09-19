"""Markdown rendering for speaker-facing content.

The markdown source is what gets stored; HTML is produced at render time and
sanitized with ``nh3`` so a script tag in a bio never reaches a page.
"""

import markdown as markdown_lib
import nh3

# Tags a bio, summary or outline may reasonably contain. Everything else,
# including script, style, iframes and event-handler attributes, is dropped.
ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
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
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "th": {"align"},
    "td": {"align"},
}


def render_md(source):
    """Render markdown ``source`` to sanitized HTML. Empty input gives ``""``."""
    if not source:
        return ""
    html = markdown_lib.markdown(source, extensions=["extra", "nl2br", "sane_lists"])
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
    )
