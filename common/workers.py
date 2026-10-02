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
predates the command answers the broadcast with an error naming it, which is
itself the finding: it runs older code than this page.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from time import monotonic

from celery import current_app
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_QUEUE = "celery"
MEDIA_QUEUE = "media"
CODE_VERSION_COMMAND = "portal_code_version"

# What a worker's answer to the version request says about its code.
CODE_CURRENT = "current"
CODE_DIFFERS = "differs"
CODE_OLDER = "older"
CODE_ERROR = "error"
CODE_SILENT = "silent"

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
    """A short fingerprint of the email code this process was started with.

    Cached for the life of the process on purpose: it names the code that was
    loaded, not the files on disk now, so editing a file and reloading shows
    the old fingerprint until a restart, which is what a page about telling
    versions apart should say. A file that cannot be read (renamed, say)
    contributes a marker instead of raising, so the page that diagnoses
    workers is never the thing that fails; a test pins that every file exists.
    """
    digest = hashlib.sha256()
    for relative in EMAIL_CODE_FILES:
        digest.update(relative.encode())
        try:
            digest.update((Path(settings.BASE_DIR) / relative).read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()[:8]


@dataclass
class Worker:
    """One worker attached to the broker."""

    name: str
    queues: tuple
    uptime: int
    started: object
    tasks: dict
    # What its answer to the version request says (``CODE_*``).
    code: str
    # The fingerprint it reported, or the error it answered with.
    version: str = ""
    error: str = ""

    @property
    def label(self):
        """The name without Celery's ``celery@`` prefix."""
        return self.name.removeprefix("celery@")

    @property
    def reads_default(self):
        return DEFAULT_QUEUE in self.queues

    @property
    def reads_media(self):
        return MEDIA_QUEUE in self.queues

    @property
    def role(self):
        if self.reads_default and self.reads_media:
            return "default and media"
        if self.reads_default:
            return "default"
        if self.reads_media:
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


def classify(version, error, web_version):
    """What a worker's answer says about its code.

    A worker without the command replies with an error that names it (a
    ``KeyError``), which is the signature of older code. Any other error is a
    worker that knows the command and failed, and no answer at all is a worker
    that was busy or gone.
    """
    if version:
        return CODE_CURRENT if version == web_version else CODE_DIFFERS
    if error:
        return CODE_OLDER if CODE_VERSION_COMMAND in error else CODE_ERROR
    return CODE_SILENT


def assess(workers, web_version):
    """The things wrong with this set of workers, as sentences."""
    problems = []
    default = [w for w in workers if w.reads_default]
    if not default:
        problems.append(
            "No worker is reading the default queue, so emails are queued and wait."
        )
    elif len(default) > 1:
        problems.append(
            f"{len(default)} workers read the default queue. A task goes to "
            "whichever takes it first, so if they run different code, some "
            "emails are sent without a record or a log line."
        )
    if not any(w.reads_media for w in workers):
        problems.append(
            "No worker is reading the media queue, so thumbnails, "
            "transcription and downloads wait."
        )
    for worker in workers:
        if worker.code == CODE_OLDER:
            problems.append(
                f"{worker.label} does not report a code version: it runs "
                "code older than this page."
            )
        elif worker.code == CODE_ERROR:
            problems.append(
                f"{worker.label} answered the version request with an error "
                f"({worker.error}), so its code version is unknown."
            )
        elif worker.code == CODE_SILENT:
            problems.append(
                f"{worker.label} did not answer the version request. It may "
                "be busy or stuck."
            )
        elif worker.code == CODE_DIFFERS:
            problems.append(
                f"{worker.label} runs different email code ({worker.version}) "
                f"from this site ({web_version})."
            )
    return problems


def inspect_workers(control=None, timeout=1.0, patience=3.0):
    """Ask the broker which workers are attached and what they run.

    The three questions are independent, so they go out together. ``timeout``
    is how long Celery waits for replies once connected; ``patience`` is the
    extra the page allows for connecting, after which the broker is reported
    as not answering. The pool is not joined on the way out: a connection to
    an address that never answers would otherwise hold the page for as long
    as the socket does. (``broker_transport_options`` bounds the connect
    itself, so such a thread ends soon after.) Never raises.
    """
    control = control or current_app.control
    web_version = email_code_version()
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        futures = (
            pool.submit(lambda: control.inspect(timeout=timeout).stats()),
            pool.submit(lambda: control.inspect(timeout=timeout).active_queues()),
            pool.submit(
                lambda: control.broadcast(
                    CODE_VERSION_COMMAND, reply=True, timeout=timeout
                )
            ),
        )
        deadline = monotonic() + timeout + patience
        stats, queues, replies = (
            future.result(timeout=max(deadline - monotonic(), 0)) for future in futures
        )
        stats, queues, replies = stats or {}, queues or {}, replies or []
    except TimeoutError:
        logger.warning("The broker did not answer for the list of workers")
        return WorkerReport(
            [],
            web_version,
            error=f"no answer from the broker within {timeout + patience:g} seconds",
        )
    except Exception as exc:
        logger.warning("Could not ask the broker for its workers: %s", exc)
        return WorkerReport([], web_version, error=f"{type(exc).__name__}: {exc}")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    versions, errors = {}, {}
    for reply in replies:
        for name, answer in reply.items():
            if "version" in answer:
                versions[name] = answer["version"]
            else:
                errors[name] = str(answer.get("error", "unexpected reply"))
    now = timezone.now()
    workers = [
        Worker(
            name=name,
            queues=tuple(q["name"] for q in queues.get(name, [])),
            uptime=info.get("uptime", 0),
            started=now - timedelta(seconds=info.get("uptime", 0)),
            tasks=info.get("total", {}),
            code=classify(versions.get(name, ""), errors.get(name, ""), web_version),
            version=versions.get(name, ""),
            error=errors.get(name, ""),
        )
        for name, info in sorted(stats.items())
    ]
    return WorkerReport(workers, web_version, assess(workers, web_version))
