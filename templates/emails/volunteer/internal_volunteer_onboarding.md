{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hello, {{ recipient_name }}. We're writing to let you know that a **new volunteer has just been approved and onboarded**.

Be sure to complete the rest of the onboarding process. They've been sent an introductory email with further instructions, however, there are some action items that you need to complete as well since not everything can be automated.

## New Team Member

The new team member is **{{ profile.user.username }}** ({{ profile.user.first_name }} {{ profile.user.last_name }}).

### Team Assignment

They have been assigned to the following team(s):

{% for team in profile.teams.all %}
- **{{ team.short_name }}**. Team Lead(s): {% for team_lead in team.team_leads.all %}{{ team_lead.user.first_name }} {{ team_lead.user.last_name }}{% if not forloop.last %}, {% endif %}{% endfor %}
{% endfor %}

### Role Assignment

They have been assigned the following role(s):

{% for role in profile.roles.all %}
- {{ role.short_name }}
{% endfor %}

## Action Items

**Please complete these tasks to complete the onboarding:**

- **Grant them the Volunteer role on Discord.** Their Discord username is: **{{ profile.discord_username }}**.

{% if profile.github_username %}
- **Add them to the [@pyladies/pyladiescon-volunteers](https://github.com/orgs/pyladies/teams/pyladiescon-volunteers) GitHub team.** Their GitHub username is: **{{ profile.github_username }}**.
{% else %}
- **⚠️ GitHub Access Pending:** They have not provided their GitHub username yet. Once they update their profile, add them to the [@pyladies/pyladiescon-volunteers](https://github.com/orgs/pyladies/teams/pyladiescon-volunteers) GitHub team.
{% endif %}

- **Say hi and welcome them on Discord.**

- **Give a shout out on social media!** Check their [Volunteer Profile](https://{{ current_site.domain }}{% url 'volunteer:volunteer_profile_detail' profile.id %}) for their social media handles.

{% if admin_onboarding %}
## Core Organizer Access

Since this is a new core-organizer, you will also need to grant them additional privileges and access, such as:

- The Organizer Role on Discord
{% if profile.github_username %}
- Add them to the [@pyladies/global-conference-organizers](https://github.com/orgs/pyladies/teams/global-conference-organizers) GitHub team (username: **{{ profile.github_username }}**)
{% else %}
- **⚠️ GitHub Access Pending:** Add them to the [@pyladies/global-conference-organizers](https://github.com/orgs/pyladies/teams/global-conference-organizers) GitHub team once they provide their GitHub username
{% endif %}
- Access to the PyLadiesCon GDrive ({{ GDRIVE_FOLDER_ID }})
- Invitation to [Jelly](https://letsjelly.com/)
- Invitation to the PyLadiesCon Regular Meeting Calendar
- Invitation to the PyLadiesCon 1Password account

**Please complete the above tasks within 5 days.** If you cannot complete these tasks, please reach out to the other core organizers on Discord.
{% endif %}

**Thank you!**

{% endblock content %}