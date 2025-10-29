{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hello, {{ recipient_name }}. We're writing to let you know that a **new Sponsorship has been added** to the system.

{% include "emails/sponsorship/sponsor_information_partial.md" with profile=profile %}

{% endblock content %}