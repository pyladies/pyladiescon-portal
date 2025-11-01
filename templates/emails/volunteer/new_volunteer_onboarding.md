{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{{ profile.user.first_name }}, thank you for applying to volunteer with PyLadiesCon. We're excited to share that your application has been approved.

## Team Assignment

You have been assigned to the following team(s):

{% for team in profile.teams.all %}
- **{{ team.short_name }}**. Team Lead(s): {% for team_lead in team.team_leads.all %}{{ team_lead.user.first_name }} {{ team_lead.user.last_name }}{% if not forloop.last %}, {% endif %}{% endfor %}
{% endfor %}

## Role Assignment

You have been assigned the following role(s):

{% for role in profile.roles.all %}
- {{ role.short_name }}
{% endfor %}

## Your Dashboard

You can review and update your volunteer profile at any time through your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}).

If you need any help, have questions, or no longer able to volunteer, please reach out to your team lead(s).

## Action Items

**Important:** Please complete these action items to activate your volunteering.

- **Join our [Discord server](https://discord.com/invite/2fUN4ddVfP)** if you haven't done so. *Failure to join the Discord server within 7 days may result in cancellation of your volunteering activity.*

- **Read the [Volunteer Guide](https://conference.pyladies.com/docs/)** to understand the roles of your team.

- **Learn the [Volunteer Roles and Responsibilities Documentation](https://conference.pyladies.com/docs/roles_and_responsibilities/)** to understand the expectations.

{% if not profile.github_username %}
- **⚠️ Update your GitHub username:** Your GitHub profile is currently missing. You will be added to the [@pyladies/pyladiescon-volunteers](https://github.com/orgs/pyladies/teams/pyladiescon-volunteers) GitHub team to access our repositories. Please update your GitHub username on the portal through your [Volunteer Dashboard](https://{{ current_site.domain }}{% url 'volunteer:index' %}) and let your team lead know after you've done that.
{% else %}
- **GitHub Access:** You will be added to the [@pyladies/pyladiescon-volunteers](https://github.com/orgs/pyladies/teams/pyladiescon-volunteers) GitHub team using your GitHub username: **{{ profile.github_username }}**. This will give you access to the PyLadiesCon repositories.
{% endif %}

{% if admin_onboarding %}
## Core Organizer Access

Since you've been added as a core organizing team (as a team lead, a staff, or admin), we will also be granting you additional privileges and access, such as:

- The Organizer Role on Discord
{% if not profile.github_username %}
- Access to the [@pyladies/global-conference-organizers](https://github.com/orgs/pyladies/teams/global-conference-organizers) GitHub team (**⚠️ Please update your GitHub username on the portal first**)
{% else %}
- Access to the [@pyladies/global-conference-organizers](https://github.com/orgs/pyladies/teams/global-conference-organizers) GitHub team
{% endif %}
- Access to the PyLadiesCon GDrive ({{ GDRIVE_FOLDER_ID }})
- Invitation to [Jelly](https://letsjelly.com/)
- Invitation to the PyLadiesCon Regular Meeting Calendar
- Invitation to the PyLadiesCon 1Password account

You should be receiving additional emails and invites to the above items within a few days. Please be sure to follow through and activate your access to the above services and items since they are crucial to our conference. If you have not received those after 5 days or if you need them sooner, please reach out to the other core organizers on Discord.
{% endif %}

**Thank you!**

{% endblock content %}