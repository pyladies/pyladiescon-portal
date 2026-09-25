{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

**{{ proposer }}** ({{ presenter.email }}) suggests a co-presenter for **{{ title }}**:

- **Name:** {{ suggested_name }}
- **Email:** {{ suggested_email }}
{% if note %}
Their note, as written:

```
{{ note }}
```
{% endif %}

Add them from the session page if you agree: {{ session_url }}

{% endblock content %}
