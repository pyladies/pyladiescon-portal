{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hello, {{ recipient_name }}.

We're writing to let you know that a new volunteer has just signed up. Be sure to review their application in a timely manner.

**Volunteer Application Status:** {{ profile.application_status }}.

## Volunteer Information

**Name:** {{ profile.user.first_name }} {{ profile.user.last_name }}

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
- **Additional Comments:** {{ profile.additional_comments }}

To approve this volunteer and assign them to your teams, click [here](https://{{ current_site.domain }}{% url 'volunteer:volunteer_profile_manage' profile.id %}).

To manage other volunteers, visit the [Volunteer Management Portal](https://{{ current_site.domain }}{% url 'volunteer:volunteer_profile_list' %}).

{% endblock content %}