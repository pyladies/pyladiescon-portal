from django import template
from django.utils.safestring import mark_safe

from speakers.markdown import render_md

register = template.Library()


@register.filter
def speaker_md(value):
    """Render a speaker-facing markdown field to sanitized HTML."""
    return mark_safe(render_md(value))
