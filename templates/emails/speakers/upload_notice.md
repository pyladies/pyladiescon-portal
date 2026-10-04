{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi,

{{ presenter.display_name }} has uploaded {% if previous %}a new version of their video{% else %}their video{% endif %} for **{{ session.title }}** ({{ conference.name }}).

- **File:** {{ asset.original_filename }}{% if asset.size_bytes %} ({{ asset.size_bytes|filesizeformat }}){% endif %}
- **Version:** {% if previous %}v{{ asset.version }}, replacing v{{ previous }}{% else %}v{{ asset.version }}, the first{% endif %}
- **Length:** being checked; the session page shows it against the limit once it is.

The file is on the session's Files section, with its preview and download: <{{ files_url }}>

The checklist board has where every session stands: <{{ board_url }}>
{% if to_liaison %}

You are getting this as {{ presenter.display_name }}'s liaison. Replying goes to them.
{% else %}

{{ presenter.display_name }} has no liaison yet, so this goes to the team. Replying goes to them.
{% endif %}

{% endblock content %}
