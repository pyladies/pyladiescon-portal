{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Good news: your session is part of {{ conference.name }}.

- **{{ session.title }}** ({{ session.kind.name }})

Your session page has the details you sent and is yours to edit until we schedule it: <{{ session_url }}>

There are a few things we need from you, and a few we are doing for you. They are all on your checklist, with the dates we need them by: <{{ checklist_url }}>

Your dashboard is the place to start: <{{ dashboard_url }}>

We will be in touch about the schedule. If anything changes on your side, reply to this email and we will sort it out.

{% endblock content %}
