from django import template
from django.utils.safestring import mark_safe

from speakers.constants import SessionStatus
from speakers.markdown import render_md
from speakers.tables import STATUS_BADGE_CLASSES

register = template.Library()


@register.filter
def speaker_md(value):
    """Render a speaker-facing markdown field to sanitized HTML."""
    return mark_safe(render_md(value))


@register.filter
def session_status_class(session):
    """Bootstrap badge class for a session's status chip."""
    return STATUS_BADGE_CLASSES[SessionStatus(session.status)]
