"""Pretix integration (design §12.1): API client, order upsert, webhook and
nightly reconciliation helpers.

Orders land in ``attendee.PretixOrder`` (the portal's existing per-edition
order record), so the speaker rules, the attendee stats and the manual link
all read the same rows.
"""

import logging
import time

import requests
from django.utils import timezone

from attendee.models import AttendeeProfile, PretixOrder, PretixOrderstatus

from .models import ActivityLog, SpeakerSettings

logger = logging.getLogger(__name__)

WEBHOOK_ACTIONS = {
    "pretix.event.order.placed",
    "pretix.event.order.paid",
    "pretix.event.order.canceled",
    "pretix.event.order.expired",
    "pretix.event.order.changed",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}


class PretixError(Exception):
    """The pretix API refused or failed after retries."""


class PretixClient:
    """Thin client over the pretix REST API with pagination and retry."""

    def __init__(self, settings_row, attempts=3, backoff=1.0):
        self.base_url = settings_row.pretix_base_url.rstrip("/") + "/"
        self.organizer = settings_row.pretix_organizer
        self.event = settings_row.pretix_event_slug
        self.headers = {"Authorization": f"Token {settings_row.pretix_api_token}"}
        self.attempts = attempts
        self.backoff = backoff

    @property
    def orders_url(self):
        return f"{self.base_url}organizers/{self.organizer}/events/{self.event}/orders/"

    def _get(self, url, params=None):
        last_error = None
        for attempt in range(self.attempts):
            try:
                response = requests.get(
                    url, headers=self.headers, params=params, timeout=30
                )
            except requests.RequestException as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = f"{response.status_code} {response.text[:200]}"
                if response.status_code not in RETRY_STATUSES:
                    break
            if attempt + 1 < self.attempts:
                time.sleep(self.backoff * (attempt + 1))
        raise PretixError(f"GET {url} failed: {last_error}")

    def get_order(self, code):
        return self._get(f"{self.orders_url}{code}/")

    def iter_orders(self, modified_since=None, email=None):
        """Yield orders page by page. ``modified_since`` is a datetime."""
        params = {}
        if modified_since is not None:
            params["modified_since"] = modified_since.isoformat()
        if email:
            params["email"] = email
        url = self.orders_url
        while url:
            page = self._get(url, params=params)
            params = None  # the ``next`` link already carries the query
            yield from page.get("results", [])
            url = page.get("next")


def upsert_order(conference, data):
    """Record one pretix order (and the attendee profile for paid orders).

    Uses the attendee app's own field mapping so both paths agree.
    """
    order, created = PretixOrder.objects.get_or_create(
        order_code=data["code"], defaults={"conference": conference}
    )
    order.from_pretix_data(data)
    # The attendee mapping re-resolves the edition from the event slug and
    # falls back to the active edition when nothing matches. This path knows
    # the edition (SpeakerSettings.pretix_event may differ from
    # Conference.pretix_event_slug on purpose), so it wins.
    order.conference = conference
    order.save()
    if order.status == PretixOrderstatus.PAID:
        profile, _ = AttendeeProfile.objects.get_or_create(order=order)
        profile.from_pretix_data(data)
        profile.save()
    return order, created


def client_for(conference):
    """A client for the edition, or None when pretix is not configured."""
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row is None or not settings_row.pretix_configured:
        return None
    return PretixClient(settings_row)


def sync_order_by_code(conference, code, client=None):
    """Re-fetch one order from pretix and upsert it (the webhook path)."""
    client = client or client_for(conference)
    order, _ = upsert_order(conference, client.get_order(code))
    return order


def reconcile(conference, client=None):
    """Page through orders modified since the last run and upsert them all.

    Returns the number of orders seen. Advances ``pretix_last_synced_at``
    to the start of the run so a webhook missed meanwhile is caught next
    time.
    """
    settings_row = SpeakerSettings.objects.get(conference=conference)
    client = client or PretixClient(settings_row)
    started = timezone.now()
    seen = 0
    for data in client.iter_orders(modified_since=settings_row.pretix_last_synced_at):
        upsert_order(conference, data)
        seen += 1
    settings_row.pretix_last_synced_at = started
    settings_row.save(update_fields=["pretix_last_synced_at", "modified_date"])
    ActivityLog.record(
        conference, "pretix.reconciled", message=f"{seen} order(s) refreshed"
    )
    return seen


def lookup_presenter_orders(presenter, actor=None, client=None):
    """Ask pretix for orders under the presenter's email and record them.

    Returns the orders found; the ``pretix_registered`` rule then ticks the
    item through the PretixOrder save signal.
    """
    client = client or client_for(presenter.conference)
    if client is None:
        return None
    orders = [
        upsert_order(presenter.conference, data)[0]
        for data in client.iter_orders(email=presenter.email)
    ]
    ActivityLog.record(
        presenter.conference,
        "pretix.lookup",
        target=presenter,
        actor=actor,
        message=f"{len(orders)} order(s) found for {presenter.email}",
    )
    return orders


def link_presenter_order(presenter, code, actor=None, client=None):
    """Point a presenter at an order by code, fetching it if unknown locally.

    A manual link wins over email matching (design §12.1).
    """
    order = PretixOrder.objects.filter(
        order_code=code, conference=presenter.conference
    ).first()
    if order is None:
        client = client or client_for(presenter.conference)
        if client is None:
            raise PretixError("Pretix is not configured for this edition.")
        order = sync_order_by_code(presenter.conference, code, client=client)
    presenter.pretix_order = order
    presenter.save(update_fields=["pretix_order", "modified_date"])
    ActivityLog.record(
        presenter.conference,
        "pretix.linked",
        target=presenter,
        actor=actor,
        message=f"Linked to order {order.order_code}",
    )
    return order


def unlink_presenter_order(presenter, actor=None):
    presenter.pretix_order = None
    presenter.save(update_fields=["pretix_order", "modified_date"])
    ActivityLog.record(
        presenter.conference, "pretix.unlinked", target=presenter, actor=actor
    )


def create_voucher(presenter):
    """Voucher creation is optional and not built yet (design §12.1).

    Behind ``SpeakerSettings.pretix_create_vouchers``: off returns None;
    on raises so nobody believes a voucher was issued.
    """
    settings_row = SpeakerSettings.objects.filter(
        conference=presenter.conference
    ).first()
    if settings_row is None or not settings_row.pretix_create_vouchers:
        return None
    raise NotImplementedError("Pretix voucher creation is not implemented yet.")
