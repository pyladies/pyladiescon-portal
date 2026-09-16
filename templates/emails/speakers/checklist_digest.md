{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ name }},

{% if for_organizer %}These organizer items are due soon (dates in {{ timezone }}):{% else %}A quick reminder of what is coming up for you (dates in {{ timezone }}):{% endif %}

{% for item in items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %} — due {{ item.due_date|date:"l j F" }}{% if item.due_date < today %} (overdue){% endif %}
{% endfor %}

{% if for_organizer %}See your queue: <{{ link }}>{% else %}Tick them off on your dashboard: <{{ link }}>{% endif %}

{% endblock content %}
