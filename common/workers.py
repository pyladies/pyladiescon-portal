"""Which Celery workers are attached to the broker, and whether they run the
same email code as this process.

Every worker reads the same queue, and a task goes to whichever takes it
first. When a release leaves an older worker running beside the new one, some
emails are sent by code that predates a change: sent without a record, or
without a log line, while the new worker's are fine. The deploy reports
success and nothing else looks wrong. This asks the broker who is attached and
lays the workers side by side so the difference is visible on one page.

A worker reports the fingerprint of the files that decide what an email task
does (``portal_code_version``, registered in ``common.tasks``). A worker that
predates the command cannot answer it, which is itself the finding: it runs
older code than this page.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from celery import current_app
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "celery"
MEDIA_QUEUE = "media"
CODE_VERSION_COMMAND = "portal_code_version"

# The files whose content decides what an email task does.
EMAIL_CODE_FILES = (
    "common/markdown_emails.py",
    "common/send_emails.py",
    "common/tasks.py",
    "speakers/emails.py",
    "speakers/tasks.py",
)


@lru_cache(maxsize=1)
def email_code_version():
    """A short fingerprint of the email code this process was started with."""
    digest = hashlib.sha256()
    for relative in EMAIL_CODE_FILES:
        digest.update(relative.encode())
        digest.update((Path(settings.BASE_DIR) / relative).read_bytes())
    return digest.hexdigest()[:8]


@dataclass
class Worker:
    """One worker attached to the broker."""

    name: str
    queues: tuple
    uptime: int
    started: object
    tasks: dict
    # Empty when the worker did not answer the version command.
    version: str

    @property
    def label(self):
        """The name without Celery's ``celery@`` prefix."""
        return self.name.removeprefix("celery@")

    @property
    def role(self):
        if DEFAULT_QUEUE in self.queues:
            return "default"
        if MEDIA_QUEUE in self.queues:
            return "media"
        return "other"

    @property
    def tasks_run(self):
        return sum(self.tasks.values())


@dataclass
class WorkerReport:
    """The workers, what is wrong with how they are set up, and this
    process's own fingerprint to compare them with."""

    workers: list
    web_version: str
    problems: list = field(default_factory=list)
    # Why the broker could not be asked, when it could not.
    error: str = ""


def assess(workers, web_version):
    """The things wrong with this set of workers, as sentences."""
    problems = []
    default = [w for w in workers if w.role == "default"]
    if not default:
        problems.append(
            "No worker is reading the default queue, so emails are queued " "and wait."
        )
    elif len(default) > 1:
        problems.append(
            f"{len(default)} workers read the default queue. A task goes to "
            "whichever takes it first, so if they run different code, some "
            "emails are sent without a record or a log line."
        )
    for worker in workers:
        if not worker.version:
            problems.append(
                f"{worker.label} does not report a code version: it runs "
                "code older than this page."
            )
        elif worker.version != web_version:
            problems.append(
                f"{worker.label} runs different email code ({worker.version}) "
                f"from this site ({web_version})."
            )
    return problems


def inspect_workers(control=None, timeout=1.0):
    """Ask the broker which workers are attached and what they run.

    The three questions are independent, so they go out together and the page
    waits for one timeout, not three. Never raises: a broker that cannot be
    reached is reported in ``error``.
    """
    control = control or current_app.control
    web_version = email_code_version()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            stats = pool.submit(lambda: control.inspect(timeout=timeout).stats())
            queues = pool.submit(
                lambda: control.inspect(timeout=timeout).active_queues()
            )
            replies = pool.submit(
                lambda: control.broadcast(
                    CODE_VERSION_COMMAND, reply=True, timeout=timeout
                )
            )
            stats, queues, replies = (
                stats.result() or {},
                queues.result() or {},
                replies.result() or [],
            )
    except Exception as exc:
        logger.warning("Could not ask the broker for its workers: %s", exc)
        return WorkerReport([], web_version, error=f"{type(exc).__name__}: {exc}")

    versions = {}
    for reply in replies:
        for name, answer in reply.items():
            versions[name] = answer.get("version", "")
    now = timezone.now()
    workers = [
        Worker(
            name=name,
            queues=tuple(q["name"] for q in queues.get(name, [])),
            uptime=info.get("uptime", 0),
            started=now - timedelta(seconds=info.get("uptime", 0)),
            tasks=info.get("total", {}),
            version=versions.get(name, ""),
        )
        for name, info in sorted(stats.items())
    ]
    return WorkerReport(workers, web_version, assess(workers, web_version))
