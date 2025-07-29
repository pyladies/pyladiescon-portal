def _send_email(subject, recipient_list, *, html_template=None, text_template=None, context=None):
    context = context or {}
    context["current_site"] = Site.objects.get_current()

    text_content = render_to_string(text_template, context)
    html_content = render_to_string(html_template, context)

    msg = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()