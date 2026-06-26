import logging

from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


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
