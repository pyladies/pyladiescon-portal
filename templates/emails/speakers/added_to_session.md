{% extends "emails/base_email.md" %}
{% load i18n tz %}
{% block content %}

Hi {{ presenter.display_name }},

Thank you for being a {{ role_word }} at {{ conference.name }}! We have added you to a session:

- **{{ session.title }}** ({{ session.kind.name }}, {{ role }}){% if starts %} — scheduled {{ starts|timezone:presenter.timezone|date:"l j F, H:i" }} {{ presenter.timezone }}{% else %} — not scheduled yet{% endif %}

Since you already accepted our invitation, you are confirmed on it: nothing to sign. The session page shows its details and the to-dos that come with it, some with due dates: <{{ session_url }}>

Your dashboard has the full picture: <{{ dashboard_url }}>

If this is a surprise or something looks off, reply to this email and we will sort it out.

{% endblock content %}
