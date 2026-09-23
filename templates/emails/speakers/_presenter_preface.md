{% load tz %}
Hi {{ presenter.display_name }},

Thank you for being a {{ role_word }} at {{ conference.name }}! These are some of your action items in preparation for the conference.
{% if sessions %}

Your session{{ sessions|length|pluralize }}:

{% for s in sessions %}
- **{{ s.title }}** ({{ s.kind }}, {{ s.role }}){% if s.starts %} — scheduled {{ s.starts|timezone:presenter.timezone|date:"l j F, H:i" }} {{ presenter.timezone }}{% else %} — not scheduled yet{% endif %}
{% endfor %}
{% endif %}
