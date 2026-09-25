{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

A new session has been proposed for {{ conference.name }}.

- **{{ title }}** ({{ session.kind.name }})
- Proposed by {{ proposer }} ({{ presenter.email }})

Read it and answer it here: <{{ review_url }}>

Approving confirms them on the session and starts their checklist, exactly as accepting an invitation does. Rejecting sends them a short note and keeps the record.

{% endblock content %}
