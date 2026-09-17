{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}
{% if for_organizer %}
Hi,

Thank you for volunteering with us at {{ conference.name }}! Here are some updates to your todo list.
{% else %}
{% include "emails/speakers/_presenter_preface.md" %}

Your todo list was updated:
{% endif %}
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

{% if for_organizer %}Go to your queue for more details: <{{ link }}>{% else %}To see more details about these action items, visit your speaker dashboard: <{{ link }}>{% endif %}

If you have already completed these tasks, mark them as done and we won't bother you with these notifications anymore.

{% endblock content %}
