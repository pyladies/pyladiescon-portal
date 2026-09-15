"""The per-edition pretix webhook receiver (design §12.1).

Pretix sends an order reference, not a signed payload, so the receiver
checks the shared secret and re-fetches the order from the API before
recording anything.
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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from portal.models import Conference

from .models import SpeakerSettings
from .pretix import WEBHOOK_ACTIONS, PretixClient, PretixError, sync_order_by_code

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def pretix_webhook(request, conference_slug):
    conference = get_object_or_404(Conference, slug=conference_slug)
    settings_row = SpeakerSettings.objects.filter(conference=conference).first()
    if settings_row is None or not settings_row.pretix_configured:
        raise Http404("Pretix is not configured for this edition.")
    if not settings_row.pretix_webhook_secret or (
        request.GET.get("secret") != settings_row.pretix_webhook_secret
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
    try:
        order = sync_order_by_code(conference, code, client=PretixClient(settings_row))
    except PretixError:
        logger.exception("Pretix webhook: could not fetch order %s", code)
        return JsonResponse({"error": "pretix unavailable"}, status=502)
    return JsonResponse({"order": order.order_code, "status": order.status})
