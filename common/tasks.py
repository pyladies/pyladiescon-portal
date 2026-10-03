import logging
import smtplib

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_ready
from celery.worker.control import control_command
from kombu.exceptions import OperationalError

from portal.process import process_name

from .models import prune_sent_emails
from .workers import email_code_version

logger = logging.getLogger(__name__)


# What a task that sends one email to one person needs, beyond a plain task.
#
# ``acks_late`` and ``reject_on_worker_lost``: a worker killed or restarted
# while it holds the task puts it back on the queue. Without them the task is
# acknowledged on receipt and a killed worker loses it without a trace, which
# is how invitations came to be marked sent and never sent. The price is that
# a task can run twice (a worker that dies after the mail server accepted the
# message), so each of these tasks checks first whether it already did.
#
# The retries cover a mail server that is down or slow for a while; an
# address the server refuses, or a login it rejects, will not get better by
# waiting. ``SMTPException`` is an ``OSError``, hence the exclusions.
EMAIL_TASK_OPTIONS = {
    "acks_late": True,
    "reject_on_worker_lost": True,
    "autoretry_for": (OSError, SoftTimeLimitExceeded),
    "dont_autoretry_for": (
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPSenderRefused,
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPNotSupportedError,
    ),
    "max_retries": 4,
    "retry_backoff": 30,
    "retry_backoff_max": 900,
    "retry_jitter": True,
    # A connection that stalls must not hold a worker process for ever.
    "soft_time_limit": 90,
    "time_limit": 120,
}


def email_task(**options):
    """``shared_task`` for a task that sends one email to one person.

    Not for a task that sends to several people (a digest, a notice to the
    organizers): a retry would send again to those who already have it.
    """
    return shared_task(**{**EMAIL_TASK_OPTIONS, **options})


@worker_ready.connect
def log_worker_ready(sender=None, **kwargs):
    """One line when a worker starts: which process, which email code.

    A worker that restarts every few minutes (killed for memory, say) shows
    here as a run of these lines, and each says which code it came up with.
    """
    logger.info(
        "Worker ready: %s process=%s email_code=%s",
        getattr(sender, "hostname", "?"),
        process_name(),
        email_code_version(),
    )


@control_command()
def portal_code_version(state):
    """Tell Maintenance > Invitations which email code this worker runs.

    A worker that predates this command cannot answer it, and the page shows
    that silence as "older code". The name must match
    ``common.workers.CODE_VERSION_COMMAND``.
    """
    return {"version": email_code_version()}


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
    A queued task logs its id, which is what the worker's own "received" and
    "succeeded" lines carry, so one search follows it across processes.
    """
    try:
        result = task.delay(*args, **kwargs)
    except OperationalError:
        logger.exception(
            "Failed to enqueue Celery task %r — broker unavailable",
            getattr(task, "name", task),
        )
    else:
        logger.info(
            "Queued %s as task %s",
            getattr(task, "name", task),
            getattr(result, "id", None),
        )
