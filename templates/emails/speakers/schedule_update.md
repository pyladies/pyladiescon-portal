{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter_name }},

The organizers just published an update to the conference schedule, and your sessions are affected:
{% for line in lines %}
- **{{ line.title }}**: {% if line.removed %}taken off the schedule for now; the team will be in touch with a new time.{% else %}{{ line.when }}{% endif %}
{% endfor %}

Your schedule page always has the current picture, in your own timezone: <{{ schedule_url }}>

{% endblock content %}
