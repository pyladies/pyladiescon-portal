{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

**{{ presenter.display_name }}** ({{ presenter.email }}) suggests a co-presenter for **{{ session.title }}**:

- **Name:** {{ suggested_name }}
- **Email:** {{ suggested_email }}
{% if note %}
> {{ note }}
{% endif %}

Add them from the session page if you agree: {{ session_url }}

{% endblock content %}
