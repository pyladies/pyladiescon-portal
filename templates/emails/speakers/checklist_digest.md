{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
{% if for_organizer %}
Hi,

Thank you for volunteering with us at {{ conference.name }}! These team todos have deadlines coming up (dates in {{ timezone }}):
{% else %}
{% include "emails/speakers/_presenter_preface.md" %}

These todos have deadlines coming up (dates in {{ timezone }}):
{% endif %}

{% for item in items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %} — due {{ item.due_date|date:"l j F" }}{% if item.due_date < today %} (overdue){% endif %}
{% endfor %}

{% if for_organizer %}Go to your queue for more details: <{{ link }}>{% else %}To see more details about these action items, visit your speaker dashboard: <{{ link }}>{% endif %}

If you have already completed these tasks, mark them as done and we won't bother you with these notifications anymore.

{% endblock content %}
