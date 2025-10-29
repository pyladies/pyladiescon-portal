{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hello, {{ recipient_name }}. We're writing to let you know that a **volunteer profile has been updated**.

## Volunteer Information

**Name:** {{ profile.user.first_name }} {{ profile.user.last_name }} ({{ profile.user.username }})

**Application Status:** {{ profile.application_status }}

### Details

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

You can view their full profile at: [Volunteer Profile](https://{{ current_site.domain }}{% url 'volunteer:volunteer_profile_detail' profile.id %}).

{% endblock content %}