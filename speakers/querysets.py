"""Shared queryset shapes for the speaker portal.

Scoping (edition, liaison) and eager loading live here so every list view
and export gets the same rows and the same query count.
"""

from django.db import models


class SessionQuerySet(models.QuerySet):
    def for_conference(self, conference):
        return self.filter(conference=conference)

    def visible_to(self, user):
        """Organizers see every session; a liaison only those with a presenter
        they look after; anyone else sees nothing."""
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(session_presenters__presenter__liaison=user).distinct()

    def with_listing_data(self):
        """Everything the sessions list renders, in a fixed number of queries."""
        from .models import SessionPresenter

        return self.select_related("kind", "slot", "slot__channel").prefetch_related(
            models.Prefetch(
                "session_presenters",
                queryset=SessionPresenter.objects.select_related(
                    "presenter", "presenter__liaison", "role"
                ).order_by("order", "id"),
                to_attr="presenter_links",
            )
        )


class PresenterQuerySet(models.QuerySet):
    def for_conference(self, conference):
        return self.filter(conference=conference)

    def visible_to(self, user):
        """Organizers see everyone; a liaison only their own presenters."""
        if user.is_superuser or user.is_staff:
            return self
        return self.filter(liaison=user)

    def with_listing_data(self):
        """Sessions, account, liaison and invitations in a fixed query count."""
        from .models import Invitation, SessionPresenter

        return self.select_related("user", "liaison").prefetch_related(
            models.Prefetch(
                "session_presenters",
                queryset=SessionPresenter.objects.select_related(
                    "session", "session__kind", "role"
                ).order_by("session__title"),
                to_attr="session_links",
            ),
            models.Prefetch(
                "invitations",
                queryset=Invitation.objects.select_related("session").order_by(
                    "-creation_date", "-id"
                ),
                to_attr="invitation_history",
            ),
        )
