{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Thank you for proposing a session for {{ conference.name }}. We have it:

- **{{ session.title }}** ({{ session.kind.name }})

The team reads every proposal and will write to you either way. There is nothing for you to do in the meantime.

You can read, change or withdraw what you sent while we are still deciding: <{{ proposals_url }}>

{% endblock content %}
