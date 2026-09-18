{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

{% if session %}We would love for you to be part of **{{ conference.name }}** with **{{ session.title }}** ({{ session.kind.name }}).{% else %}We would love for you to be part of **{{ conference.name }}**.{% endif %}

{% if invitation.message_md %}
{{ invitation.message_md }}

{% endif %}
**[Accept or decline the invitation]({{ accept_url }})**

If the button does not work, copy this address into your browser: {{ accept_url }}

This link is personal to you and works until {{ expires_at|date:"j F Y" }}. Accepting creates your speaker account on the portal, where you can fill in your bio and session details and see what happens next.

If you have any questions, just reply to this email.

{% endblock content %}
