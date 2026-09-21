"""The per-edition pretix webhook receiver (design §12.1).

Pretix sends an order reference, not a signed payload, so the receiver
checks the shared secret (constant-time), the organizer and the event, and
queues a task that re-fetches the order from the API before recording it.
"""

import json
import logging

from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from portal.models import Conference

from .encryption import usable
from .models import SpeakerSettings
from .pretix import WEBHOOK_ACTIONS
from .tasks import sync_order_task

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def pretix_webhook(request, conference_slug):
    conference = get_object_or_404(Conference, slug=conference_slug)
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row is None or not settings_row.pretix_configured:
        raise Http404("Pretix is not configured for this edition.")
    secret = settings_row.pretix_webhook_secret
    if not usable(secret) or not constant_time_compare(
        request.GET.get("secret", ""), secret
    ):
        return HttpResponse("Unauthorized", status=401)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON")
    action = payload.get("action")
    code = payload.get("code")
    if not code or action not in WEBHOOK_ACTIONS:
        return HttpResponseBadRequest("Unsupported payload")
    if payload.get("event") and payload["event"] != settings_row.pretix_event_slug:
        return HttpResponseBadRequest("Wrong event")
    if (
        payload.get("organizer")
        and payload["organizer"] != settings_row.pretix_organizer
    ):
        return HttpResponseBadRequest("Wrong organizer")
    # Validate, queue, answer. The round-trip to pretix (with its retries)
    # runs in the worker, so a slow pretix never ties up a web worker during
    # a ticket-sale burst, and pretix retries the delivery itself if the
    # queueing fails.
    try:
        sync_order_task.delay(conference.pk, code)
    except Exception:  # noqa: BLE001 - broker down, or the task itself in eager mode
        logger.exception("Pretix webhook: could not queue order %s", code)
        return JsonResponse({"error": "could not queue"}, status=502)
    logger.info("Pretix webhook: queued %s for %s", code, conference)
    return JsonResponse({"queued": code}, status=202)
