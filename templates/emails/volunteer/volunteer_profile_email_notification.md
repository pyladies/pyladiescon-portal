{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ profile.user.first_name }}, thank you for applying to volunteer with us.

{% if updated %}
Your volunteer profile has recently been updated.
{% endif %}

## Application Status

Your current volunteer application status: **{{ profile.application_status }}**.

## Your Information

- **Availability:** {{ profile.availability_hours_per_week }} hours per week
- **GitHub username:** {{ profile.github_username }}
- **Discord username:** {{ profile.discord_username }}
- **Instagram username:** {{ profile.instagram_username }}
- **Bluesky username:** {{ profile.bluesky_username }}
- **Mastodon URL:** {{ profile.mastodon_url }}
- **X username:** {{ profile.x_username }}
- **LinkedIn URL:** {{ profile.linkedin_url }}
- **PyLadies Chapter:** {{ profile.chapter }}
- **Region:** {{ profile.region }}
- **Languages spoken:** {{ profile.languages_spoken|join:", " }}
- **Additional Comments:** {{ profile.additional_comments }}

If you would like to review or update your application at any time, go to your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}).

{% endblock content %}