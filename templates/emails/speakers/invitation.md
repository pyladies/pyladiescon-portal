{% extends "emails/base_email.md" %}
{% load i18n %}
{% block content %}

Hi {{ presenter.display_name }},

{% if session %}We would love for you to be part of **{{ conference.name }}** with **{{ session.title }}** ({{ session.kind.name }}).{% else %}We would love for you to be part of **{{ conference.name }}**.{% endif %}

{% if invitation.message_md %}
Below is a message from {% firstof sender "the organizing team" %}:

{% if preview %}<div class="invitation-preview-note" markdown="1">
{{ invitation.message_md }}
</div>{% else %}{{ invitation.message_md }}{% endif %}

{% elif preview %}
{% comment %}Preview only (the sent email never takes this branch): where the sender's words would go. In the branch above, md_in_html (part of the "extra" extension) renders the markdown inside the box.{% endcomment %}
<div class="invitation-preview-note" markdown="1">
*Your personal message, if you write one, goes here, introduced with "Below is a message from {{ sender }}:".*
</div>

{% endif %}
**[Accept or decline the invitation]({{ accept_url }})**

{% comment %}
The angle brackets make the address a Markdown autolink. The plain-text
part of the email is the Markdown source with link targets dropped, so
without them the bare button above would leave that part with no usable
address. Keep them.
{% endcomment %}
If the button does not work, copy this address into your browser: <{{ accept_url }}>

This link is personal to you and works until {{ expires_at|date:"j F Y" }}. Accepting creates your speaker account on the portal, where you can fill in your bio and session details and see what happens next.

If you have any questions, just reply to this email.

{% endblock content %}
