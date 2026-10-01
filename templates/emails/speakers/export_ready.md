{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

{% blocktranslate with name=conference.name count=export.file_count %}Your file export for {{ name }} is ready: {{ count }} files in one zip, with the manifest inside.{% endblocktranslate %}

[{% trans "Download the zip" %}]({{ link }})

{% trans "If the link above does not open, copy this address into your browser:" %}
{{ link }}

{% blocktranslate with when=expires_at|date:"j M Y H:i" %}The link works until {{ when }} UTC and fetches the files for whoever has it, so keep it to yourself.{% endblocktranslate %}
{% endblock content %}
