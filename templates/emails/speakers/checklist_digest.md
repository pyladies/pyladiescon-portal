{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
{% if for_organizer %}
Hi,

Thank you for volunteering with us at {{ conference.name }}! These team todos have deadlines coming up (dates in {{ timezone }}):
{% else %}
{% include "emails/speakers/_presenter_preface.md" %}
{% if items %}

These todos have deadlines coming up (dates in {{ timezone }}):
{% endif %}
{% endif %}
{% if items %}

{% for item in items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %} — due {{ item.due_date|date:"l j F" }}{% if item.due_date < today %} (overdue){% endif %}
{% endfor %}

{% if for_organizer %}Go to your queue for more details: <{{ link }}>{% else %}To see more details about these action items, visit your speaker dashboard: <{{ link }}>{% endif %}

If you have already completed these tasks, mark them as done and we won't bother you with these notifications anymore.
{% endif %}
{% if shared_sessions %}

{% if items %}The team has also shared new files with you:{% else %}The team has shared new files with you:{% endif %}
{% for s in shared_sessions %}

**{{ s.title }}**
{% for f in s.files %}
- {{ f.display_title }}{% if f.title %} ({{ f.label }}){% endif %}, v{{ f.version }}{% if f.shared_at %}, shared {{ f.shared_at|date:"j F" }}{% endif %}
{% endfor %}

See and download them on your session page: <{{ s.link }}>
{% endfor %}
{% endif %}

{% endblock content %}
