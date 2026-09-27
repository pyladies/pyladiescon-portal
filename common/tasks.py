import logging

from celery import shared_task
from kombu.exceptions import OperationalError

from .models import prune_sent_emails

logger = logging.getLogger(__name__)


@shared_task
def prune_email_records_task():
    """Delete email records past retention.

    Scheduled through django-celery-beat (the "Prune email records" periodic
    task seeded by common's first migration); the return value is what the
    task result and the worker log record.
    """
    count = prune_sent_emails()
    return f"Deleted {count} email record(s) past retention"


def enqueue(task, *args, **kwargs):
    """Queue a Celery task without letting a broker outage break the caller.

    Sending email is a side effect of the triggering request (a profile save,
    an approval, a cancellation). If the broker is unreachable, log it (so it
    surfaces in Sentry) rather than raising and 500-ing the user's action.
    """
    try:
        task.delay(*args, **kwargs)
    except OperationalError:
        logger.exception(
            "Failed to enqueue Celery task %r — broker unavailable",
            getattr(task, "name", task),
        )
