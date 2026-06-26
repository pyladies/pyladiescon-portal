import logging

from kombu.exceptions import OperationalError

from common.tasks import enqueue


class _RecordingTask:
    name = "recording.task"

    def __init__(self):
        self.calls = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class _FailingTask:
    name = "failing.task"

    def delay(self, *args, **kwargs):
        raise OperationalError("broker unavailable")


def test_enqueue_calls_delay():
    task = _RecordingTask()
    enqueue(task, 1, 2, x=3)
    assert task.calls == [((1, 2), {"x": 3})]


def test_enqueue_swallows_broker_error(caplog):
    with caplog.at_level(logging.ERROR):
        enqueue(_FailingTask())  # must not raise
    assert "Failed to enqueue" in caplog.text
