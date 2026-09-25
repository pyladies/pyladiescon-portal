{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Good news: your session is part of {{ conference.name }}.

- **{{ session.title }}** ({{ session.kind.name }})

Your session page has the details you sent and is yours to edit until we schedule it: <{{ session_url }}>

There are a few action items we need from you to prepare for your session. We have put together a checklist for you, with the dates we need each one by: <{{ checklist_url }}>

Sign in to your dashboard to see it all in one place and to learn more: <{{ dashboard_url }}>

We will be in touch about the schedule. If anything changes on your side, reply to this email and we will sort it out.

{% endblock content %}
