{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ profile.user.first_name }}, thank you for applying to volunteer with us.

{% if updated %}
Your volunteer profile has recently been updated.
{% endif %}

## Application Status

We received many volunteer applications, and we're not able to accept everyone. At this time, the team you've applied for is **at full capacity**.

We are placing you on a **waitlist** in case the volunteer opportunity opens up in the future.

Thank you for your understanding and for your interest in volunteering with us!

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
- **Additional Comments:** {{ profile.additional_comments }}

If you would like to review or update your application at any time, go to your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}).

{% endblock content %}