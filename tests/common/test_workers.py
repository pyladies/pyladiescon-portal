from celery.worker.control import Panel
from django.utils import timezone

from common import workers
from common.workers import (
    CODE_VERSION_COMMAND,
    DEFAULT_QUEUE,
    MEDIA_QUEUE,
    Worker,
    assess,
    email_code_version,
    inspect_workers,
)

WEB = email_code_version()


def worker(name, queue=DEFAULT_QUEUE, version=WEB, tasks=None, uptime=60):
    return Worker(
        name=f"celery@{name}",
        queues=(queue,),
        uptime=uptime,
        started=timezone.now(),
        tasks=tasks or {},
        version=version,
    )


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

    def test_every_file_it_reads_exists(self, settings):
        for relative in workers.EMAIL_CODE_FILES:
            assert (settings.BASE_DIR / relative).is_file(), relative


class TestControlCommand:
    def test_workers_answer_with_their_fingerprint(self):
        command = Panel.data[CODE_VERSION_COMMAND]
        assert command(None) == {"version": email_code_version()}


class TestWorker:
    def test_label_drops_the_celery_prefix(self):
        assert worker("w-1").label == "w-1"

    def test_role_comes_from_the_queue(self):
        assert worker("a").role == "default"
        assert worker("b", queue=MEDIA_QUEUE).role == "media"
        assert worker("c", queue="other").role == "other"

    def test_tasks_run_adds_up(self):
        assert worker("a", tasks={"x": 2, "y": 3}).tasks_run == 5


class TestAssess:
    def test_one_default_worker_on_the_same_code_is_fine(self):
        assert assess([worker("a"), worker("m", queue=MEDIA_QUEUE)], WEB) == []

    def test_no_default_worker(self):
        problems = assess([worker("m", queue=MEDIA_QUEUE)], WEB)
        assert problems == [
            "No worker is reading the default queue, so emails are queued and wait."
        ]

    def test_no_workers_at_all(self):
        assert len(assess([], WEB)) == 1

    def test_two_default_workers(self):
        problems = assess([worker("a"), worker("b")], WEB)
        assert len(problems) == 1
        assert problems[0].startswith("2 workers read the default queue")

    def test_a_worker_that_reports_nothing_is_older_code(self):
        problems = assess([worker("a"), worker("old", version="")], WEB)
        assert any("old does not report a code version" in p for p in problems)

    def test_a_worker_on_different_code_is_named(self):
        problems = assess([worker("a", version="deadbeef")], WEB)
        assert problems == [
            f"a runs different email code (deadbeef) from this site ({WEB})."
        ]


class TestInspectWorkers:
    def stats(self, *names):
        return {f"celery@{n}": {"uptime": 100, "total": {"t": 2}} for n in names}

    def test_lays_the_workers_side_by_side(self):
        control = FakeControl(
            stats=self.stats("new", "old", "media"),
            queues={
                "celery@new": [{"name": DEFAULT_QUEUE}],
                "celery@old": [{"name": DEFAULT_QUEUE}],
                "celery@media": [{"name": MEDIA_QUEUE}],
            },
            replies=[
                {"celery@new": {"version": WEB}},
                {"celery@media": {"version": WEB}},
            ],
        )
        report = inspect_workers(control, timeout=0.5)
        assert [w.label for w in report.workers] == ["media", "new", "old"]
        assert [w.role for w in report.workers] == ["media", "default", "default"]
        assert [w.version for w in report.workers] == [WEB, WEB, ""]
        assert report.workers[0].tasks == {"t": 2}
        assert report.workers[0].uptime == 100
        assert report.web_version == WEB
        assert report.error == ""
        assert any("old does not report" in p for p in report.problems)
        assert any("2 workers read the default queue" in p for p in report.problems)
        assert control.asked == [(CODE_VERSION_COMMAND, True, 0.5)]

    def test_nobody_answering_is_no_workers(self):
        report = inspect_workers(FakeControl(stats=None, queues=None, replies=None))
        assert report.workers == []
        assert report.error == ""
        assert report.problems == [
            "No worker is reading the default queue, so emails are queued and wait."
        ]

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

    def test_a_reply_without_a_version_counts_as_none(self):
        report = inspect_workers(
            FakeControl(
                stats=self.stats("a"),
                queues={"celery@a": [{"name": DEFAULT_QUEUE}]},
                replies=[{"celery@a": {"error": "boom"}}],
            )
        )
        assert report.workers[0].version == ""
