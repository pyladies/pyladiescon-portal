{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ presenter.display_name }} has added a session to {{ conference.name }}:

- **{{ session.title }}** ({{ session.kind.name }})

They are already a speaker on the program, so the session is a draft with them confirmed on it and their checklist started. It is not public and not on the schedule until you put it there.

The session page is here: <{{ session_url }}>

{% endblock content %}
