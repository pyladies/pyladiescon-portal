{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
{% if for_organizer %}
Hi,

These organizer items are due soon (dates in {{ timezone }}):
{% else %}
{% include "emails/speakers/_presenter_preface.md" %}

These todos have deadlines coming up (dates in {{ timezone }}):
{% endif %}

{% for item in items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %} — due {{ item.due_date|date:"l j F" }}{% if item.due_date < today %} (overdue){% endif %}
{% endfor %}

{% if for_organizer %}See your queue: <{{ link }}>{% else %}To see more details about these action items, visit your speaker dashboard: <{{ link }}>{% endif %}

{% endblock content %}
