{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

There has been an **update to the sponsorship profile** for {{ profile.organization_name }}.

Please review the changes.

{% include "emails/sponsorship/sponsor_information_partial.md" with profile=profile %}

{% endblock content %}