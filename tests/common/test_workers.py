import threading
import time

from celery.worker.control import Panel
from django.utils import timezone

from common import workers
from common.workers import (
    CODE_CURRENT,
    CODE_DIFFERS,
    CODE_ERROR,
    CODE_OLDER,
    CODE_SILENT,
    CODE_VERSION_COMMAND,
    DEFAULT_QUEUE,
    MEDIA_QUEUE,
    Worker,
    assess,
    classify,
    email_code_version,
    inspect_workers,
)

WEB = email_code_version()
NO_MEDIA = "No worker is reading the media queue, so thumbnails, transcription and downloads wait."
NO_DEFAULT = "No worker is reading the default queue, so emails are queued and wait."


def worker(name, queues=(DEFAULT_QUEUE,), code=CODE_CURRENT, version=WEB, **kw):
    return Worker(
        name=f"celery@{name}",
        queues=tuple(queues),
        uptime=60,
        started=timezone.now(),
        tasks=kw.pop("tasks", {}),
        code=code,
        version=version,
        **kw,
    )


def healthy():
    return [worker("web-1"), worker("media-1", queues=(MEDIA_QUEUE,))]


class FakeInspect:
    def __init__(self, stats, queues):
        self._stats, self._queues = stats, queues

    def stats(self):
        return self._stats

    def active_queues(self):
        return self._queues


class FakeControl:
    """Answers like a broker with the given workers attached."""

    def __init__(self, stats=None, queues=None, replies=None, error=None):
        self.args = (stats, queues)
        self.replies = replies
        self.error = error
        self.asked = []

    def inspect(self, timeout):
        if self.error:
            raise self.error
        return FakeInspect(*self.args)

    def broadcast(self, command, reply, timeout):
        self.asked.append((command, reply, timeout))
        return self.replies


class HungControl:
    """A broker that never answers: every question blocks."""

    def __init__(self):
        self.release = threading.Event()

    def inspect(self, timeout):
        self.release.wait(30)
        return FakeInspect({}, {})

    def broadcast(self, command, reply, timeout):
        self.release.wait(30)
        return []


class TestFingerprint:
    def test_is_short_and_stable(self):
        assert len(email_code_version()) == 8
        assert email_code_version() == email_code_version()

    def test_changes_with_the_code(self, tmp_path, settings):
        (tmp_path / "common").mkdir()
        (tmp_path / "speakers").mkdir()
        for relative in workers.EMAIL_CODE_FILES:
            (tmp_path / relative).write_text("one")
        settings.BASE_DIR = tmp_path
        email_code_version.cache_clear()
        try:
            before = email_code_version()
            (tmp_path / "speakers/tasks.py").write_text("two")
            email_code_version.cache_clear()
            assert email_code_version() != before
        finally:
            email_code_version.cache_clear()

    def test_a_missing_file_does_not_raise(self, tmp_path, settings):
        settings.BASE_DIR = tmp_path
        email_code_version.cache_clear()
        try:
            assert len(email_code_version()) == 8
            assert email_code_version() != WEB
        finally:
            email_code_version.cache_clear()

    def test_every_file_it_reads_exists(self, settings):
        """The fingerprint tolerates a missing file, but a rename should fail
        the suite, not silently change what is fingerprinted."""
        for relative in workers.EMAIL_CODE_FILES:
            assert (settings.BASE_DIR / relative).is_file(), relative


class TestSettings:
    def test_the_broker_connect_is_bounded(self, settings):
        timeout = settings.CELERY_BROKER_TRANSPORT_OPTIONS["socket_connect_timeout"]
        assert 0 < timeout <= 10


class TestControlCommand:
    def test_workers_answer_with_their_fingerprint(self):
        command = Panel.data[CODE_VERSION_COMMAND]
        assert command(None) == {"version": email_code_version()}


class TestWorker:
    def test_label_drops_the_celery_prefix(self):
        assert worker("w-1").label == "w-1"

    def test_role_comes_from_the_queues(self):
        assert worker("a").role == "default"
        assert worker("b", queues=(MEDIA_QUEUE,)).role == "media"
        assert worker("c", queues=(DEFAULT_QUEUE, MEDIA_QUEUE)).role == (
            "default and media"
        )
        assert worker("d", queues=("other",)).role == "other"

    def test_tasks_run_adds_up(self):
        assert worker("a", tasks={"x": 2, "y": 3}).tasks_run == 5


class TestClassify:
    def test_the_same_fingerprint_is_current(self):
        assert classify(WEB, "", WEB) == CODE_CURRENT

    def test_another_fingerprint_differs(self):
        assert classify("deadbeef", "", WEB) == CODE_DIFFERS

    def test_an_error_naming_the_command_is_older_code(self):
        error = "KeyError('portal_code_version')"
        assert classify("", error, WEB) == CODE_OLDER

    def test_any_other_error_is_an_error(self):
        assert classify("", "RuntimeError('boom')", WEB) == CODE_ERROR

    def test_no_answer_is_silent(self):
        assert classify("", "", WEB) == CODE_SILENT


class TestAssess:
    def test_one_default_and_one_media_worker_on_the_same_code_is_fine(self):
        assert assess(healthy(), WEB) == []

    def test_one_worker_reading_both_queues_is_fine(self):
        both = worker("dev", queues=(DEFAULT_QUEUE, MEDIA_QUEUE))
        assert assess([both], WEB) == []

    def test_no_default_worker(self):
        assert assess([worker("m", queues=(MEDIA_QUEUE,))], WEB) == [NO_DEFAULT]

    def test_no_media_worker(self):
        assert assess([worker("a")], WEB) == [NO_MEDIA]

    def test_no_workers_at_all(self):
        assert assess([], WEB) == [NO_DEFAULT, NO_MEDIA]

    def test_two_default_workers(self):
        problems = assess(healthy() + [worker("web-2")], WEB)
        assert len(problems) == 1
        assert problems[0].startswith("2 workers read the default queue")

    def test_a_combined_worker_counts_as_default(self):
        both = worker("dev", queues=(DEFAULT_QUEUE, MEDIA_QUEUE))
        problems = assess([worker("a"), both], WEB)
        assert problems[0].startswith("2 workers read the default queue")

    def test_older_code(self):
        old = worker("old", code=CODE_OLDER, version="")
        assert assess(healthy() + [old], WEB)[-1] == (
            "old does not report a code version: it runs code older than " "this page."
        )

    def test_an_error_is_not_called_old_code(self):
        bad = worker("bad", code=CODE_ERROR, version="", error="RuntimeError('x')")
        problems = [p for p in assess(healthy() + [bad], WEB) if "bad" in p]
        assert problems == [
            "bad answered the version request with an error "
            "(RuntimeError('x')), so its code version is unknown."
        ]

    def test_silence_is_not_called_old_code(self):
        quiet = worker("quiet", code=CODE_SILENT, version="")
        problems = [p for p in assess(healthy() + [quiet], WEB) if "quiet" in p]
        assert problems == [
            "quiet did not answer the version request. It may be busy or stuck."
        ]

    def test_different_code_is_named(self):
        other = worker("other", code=CODE_DIFFERS, version="deadbeef")
        assert assess(healthy() + [other], WEB)[-1] == (
            f"other runs different email code (deadbeef) from this site ({WEB})."
        )


class TestInspectWorkers:
    def stats(self, *names):
        return {f"celery@{n}": {"uptime": 100, "total": {"t": 2}} for n in names}

    def test_lays_the_workers_side_by_side(self):
        control = FakeControl(
            stats=self.stats("new", "old", "media", "mute", "bad"),
            queues={
                "celery@new": [{"name": DEFAULT_QUEUE}],
                "celery@old": [{"name": DEFAULT_QUEUE}],
                "celery@bad": [{"name": DEFAULT_QUEUE}],
                "celery@mute": [{"name": DEFAULT_QUEUE}],
                "celery@media": [{"name": MEDIA_QUEUE}],
            },
            replies=[
                {"celery@new": {"version": WEB}},
                {"celery@media": {"version": WEB}},
                {"celery@old": {"error": "KeyError('portal_code_version')"}},
                {"celery@bad": {"error": "RuntimeError('boom')"}},
            ],
        )
        report = inspect_workers(control, timeout=0.5)
        assert [w.label for w in report.workers] == [
            "bad",
            "media",
            "mute",
            "new",
            "old",
        ]
        assert [w.code for w in report.workers] == [
            CODE_ERROR,
            CODE_CURRENT,
            CODE_SILENT,
            CODE_CURRENT,
            CODE_OLDER,
        ]
        assert report.workers[1].role == "media"
        assert report.workers[1].tasks == {"t": 2}
        assert report.workers[1].uptime == 100
        assert report.workers[4].error == "KeyError('portal_code_version')"
        assert report.web_version == WEB
        assert report.error == ""
        assert len(report.problems) == 4
        assert control.asked == [(CODE_VERSION_COMMAND, True, 0.5)]

    def test_nobody_answering_is_no_workers(self):
        report = inspect_workers(FakeControl(stats=None, queues=None, replies=None))
        assert report.workers == []
        assert report.error == ""
        assert report.problems == [NO_DEFAULT, NO_MEDIA]

    def test_a_worker_with_no_queues_listed_reads_nothing(self):
        report = inspect_workers(
            FakeControl(stats=self.stats("a"), queues={}, replies=[])
        )
        assert report.workers[0].queues == ()
        assert report.workers[0].role == "other"

    def test_an_unreachable_broker_is_reported_not_raised(self, caplog):
        report = inspect_workers(FakeControl(error=ConnectionError("refused")))
        assert report.workers == []
        assert report.error == "ConnectionError: refused"
        assert "refused" in caplog.text

    def test_a_broker_that_never_answers_does_not_hold_the_page(self, caplog):
        control = HungControl()
        try:
            started = time.monotonic()
            report = inspect_workers(control, timeout=0.05, patience=0.2)
            took = time.monotonic() - started
        finally:
            control.release.set()
        assert took < 3
        assert report.workers == []
        assert report.error == "no answer from the broker within 0.25 seconds"
        assert "did not answer" in caplog.text

    def test_a_worker_without_uptime_or_totals_still_lists(self):
        report = inspect_workers(
            FakeControl(
                stats={"celery@a": {}},
                queues={"celery@a": [{"name": DEFAULT_QUEUE}]},
                replies=[{"celery@a": {"version": WEB}}],
            )
        )
        assert report.workers[0].uptime == 0
        assert report.workers[0].tasks == {}

    def test_a_reply_with_neither_a_version_nor_an_error_is_unexpected(self):
        report = inspect_workers(
            FakeControl(
                stats=self.stats("a"),
                queues={"celery@a": [{"name": DEFAULT_QUEUE}]},
                replies=[{"celery@a": {}}],
            )
        )
        assert report.workers[0].code == CODE_ERROR
        assert report.workers[0].error == "unexpected reply"
