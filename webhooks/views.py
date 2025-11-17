import json
import logging
from functools import wraps

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from attendee.models import PretixOrder
from common.pretix_wrapper import (
    PRETIX_ALLOWED_WEBHOOK_ACTIONS,
    PRETIX_EVENT_SLUG,
    PRETIX_ORG,
    PretixWrapper,
)

logger = logging.getLogger(__name__)


def require_webhook_secret(param_name):
    """
    Decorator to ensure the webhook secret query parameter is present in the request.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if param_name not in request.GET:
                return HttpResponseBadRequest(
                    f"Missing required query parameter: {param_name}"
                )
            else:
                param_value = request.GET[param_name]
                if param_value != settings.PRETIX_WEBHOOK_SECRET:
                    return HttpResponse("Unauthorized", status=401)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def require_pretix_payload():
    """
    Decorator to ensure the request contains a valid pretix payload.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            event_json = json.loads(request.body.decode("utf-8"))
            logger.info(f"Pretix webhook payload: {event_json}")
            # Basic validation of pretix payload structure
            required_keys = {"notification_id", "organizer", "event", "code", "action"}
            if not required_keys.issubset(event_json.keys()):
                logger.exception("Invalid pretix payload structure, %s", event_json)
                return HttpResponseBadRequest("Invalid pretix payload structure")
            if event_json["action"] not in PRETIX_ALLOWED_WEBHOOK_ACTIONS:
                logger.exception("Unsupported pretix action, %s", event_json)
                return HttpResponseBadRequest("Unsupported pretix action")
            if event_json["organizer"] != PRETIX_ORG:
                logger.exception("Invalid organizer, %s", event_json)
                return HttpResponseBadRequest("Invalid organizer")
            if event_json["event"] != PRETIX_EVENT_SLUG:
                logger.exception("Invalid event slug, %s", event_json)
                return HttpResponseBadRequest("Invalid event slug")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


@csrf_exempt
@require_POST
@require_webhook_secret("secret")
@require_pretix_payload()
def pretix_webhook(request):
    """
    Webhook from pretix to notify about order updates.
    Only handle order paid and order canceled so that we can update our stats accordingly.
    """
    context = {}
    pretix_wrapper = PretixWrapper(PRETIX_ORG, PRETIX_EVENT_SLUG)
    event_json = json.loads(request.body.decode("utf-8"))
    order_code = event_json["code"]
    order_data = pretix_wrapper.get_order_by_code(order_code)
    order_instance, _ = PretixOrder.objects.get_or_create(order_code=order_code)
    order_instance.from_pretix_data(order_data)
    order_instance.save()

    return JsonResponse(context)
