{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi,

{% if for_organizer %}The organizer checklist items you look after have changed.{% else %}The organizers updated your checklist.{% endif %}
{% if new_items %}

## New

{% for item in new_items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %}{% if item.due_date %} — due {{ item.due_date|date:"l j F" }}{% endif %}
{% endfor %}
{% endif %}
{% if changed_items %}

## Changed

{% for item in changed_items %}
- **{{ item.title }}**{% if item.session %} — {{ item.session.title }}{% endif %}{% if for_organizer and item.presenter %} — for {{ item.presenter.display_name }}{% endif %}{% if item.due_date %} — now due {{ item.due_date|date:"l j F" }}{% endif %}
{% endfor %}
{% endif %}

{% if for_organizer %}See your queue: <{{ link }}>{% else %}See the full list on your dashboard: <{{ link }}>{% endif %}

{% endblock content %}
