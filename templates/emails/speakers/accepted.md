{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Thank you for accepting! Here is everything you need to get going with **{{ conference.name }}**.

## Your account

- **Username:** {{ user.username }}
- **Email:** {{ presenter.email }}

To sign in again, use **Send me a sign-in code** on the login page and we will email you a code: <{{ login_url }}>

If you prefer a password, set one here: <{{ password_url }}>
{% if sessions %}

## Your session{{ sessions|length|pluralize }}

{% for link in sessions %}
- **{{ link.session.title }}** ({{ link.session.kind.name }}, {{ link.role.name|lower }})
{% endfor %}
{% endif %}

## What happens next

Your dashboard lists what we need from you before the conference, with due dates, and what the team is doing for you: <{{ dashboard_url }}>

Please check it now and again; we will also email reminders as dates approach.

See you there!

{% endblock content %}
