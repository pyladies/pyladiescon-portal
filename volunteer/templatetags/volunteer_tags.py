from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def render_volunteer_languages(volunteer_profile, css_classes="badge bg-info text-dark me-1"):
    """
    Renders volunteer languages as badges.
    
    Args:
        volunteer_profile: VolunteerProfile instance with language relationship
        css_classes: CSS classes for the badge styling (optional)
    
    Returns:
        Safe HTML string with language badges
    """
    if not volunteer_profile or not hasattr(volunteer_profile, 'language'):
        return ""
    
    languages = volunteer_profile.language.all()
    if not languages:
        return ""
    
    badge_html = []
    for language in languages:
        badge_html.append(f'<span class="{css_classes}">{language.name}</span>')
    
    return mark_safe(" ".join(badge_html))


@register.inclusion_tag('volunteer/templatetags/volunteer_languages.html')
def volunteer_languages_badges(volunteer_profile, css_classes="badge bg-info text-dark me-1"):
    """
    Inclusion tag to render volunteer languages using a template.
    
    Args:
        volunteer_profile: VolunteerProfile instance with language relationship
        css_classes: CSS classes for the badge styling (optional)
    
    Returns:
        Context dictionary for the template
    """
    languages = []
    if volunteer_profile and hasattr(volunteer_profile, 'language'):
        languages = volunteer_profile.language.all()
    
    return {
        'languages': languages,
        'css_classes': css_classes,
    }