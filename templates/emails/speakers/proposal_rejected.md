{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

Thank you for proposing **{{ session.title }}** for {{ conference.name }}. We are not able to take it this time.

We had more proposals than places, and turning one down says nothing about you or the work. We would be glad to see you propose again another year, and we hope you will join us at the conference.

{% endblock content %}
