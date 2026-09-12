"""django-allauth adapter hooks for the portal."""

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class PortalAccountAdapter(DefaultAccountAdapter):
    """Add portal-wide values to the context of every account email.

    ``unverified_account_retention_days`` lets the verification email tell the
    recipient how long an unverified account survives before it is deleted, so
    the number in the email and the number the cleanup job uses can never
    disagree.
    """

    def send_mail(self, template_prefix, email, context):
        days = settings.UNVERIFIED_ACCOUNT_RETENTION_DAYS
        context = {"unverified_account_retention_days": days, **context}
        super().send_mail(template_prefix, email, context)
