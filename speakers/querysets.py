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

    def onboarded(self):
        """On the program: a confirmed link to a session of this edition.

        Someone whose proposal has not been answered has a presenter row
        and no place on the program, which is why the speaker area and the
        agreements gate ask this rather than whether the row exists.
        """
        return self.filter(session_presenters__confirmed_at__isnull=False).distinct()

    def not_only_proposing(self):
        """Everyone the organizers are working with.

        Looser than ``onboarded``: a presenter an organizer created but has
        not invited yet is still their work, and so is one with an
        invitation outstanding, whatever else they have proposed. What
        does not belong is someone whose every session is still a
        proposal or a refused one: a presenter row with no checklist
        behind it, and an empty line reads as work that has gone missing.
        """
        from .constants import UNACCEPTED_STATUSES
        from .models import SessionPresenter

        links = SessionPresenter.objects.filter(presenter=models.OuterRef("pk"))
        return self.annotate(
            _linked=models.Exists(links),
            _on_program=models.Exists(
                links.exclude(session__status__in=UNACCEPTED_STATUSES)
            ),
        ).filter(models.Q(_on_program=True) | models.Q(_linked=False))

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
