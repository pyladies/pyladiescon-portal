{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Dear {{ profile.user.first_name|default:profile.user.username }},

This email confirms that your Volunteer application for PyLadiesCon has been cancelled.

## Changes Made

Your Volunteer Profile status has been set to **"Cancelled"**

{% if teams_removed %}
You have been removed from the following teams:

{% for team in teams_removed %}- {{ team.short_name }} {% endfor %}

{% endif %}

{% if roles_removed %}
You have been removed from the following roles:

{% for role in roles_removed %}- {{ role.short_name }} {% endfor %}

{% endif %}

Team leads have been notified of your departure.

Your access to volunteer resources will be revoked within the next 24 hours.

We understand that circumstances can change, and we appreciate the time you were willing to dedicate to PyLadiesCon.

If you change your mind in the future and would like to volunteer again,
you're welcome to submit a new volunteer application through our portal.

If this was a mistake, or you do not wish to cancel your application, please contact us so that we
can rectify the situation.

Thank you for your interest in PyLadiesCon, and we hope to see you as a participant or volunteer in future events!

Best regards.

{% endblock content %}