"""Fixtures shared by the speakers tests."""

from unittest.mock import MagicMock

import pytest
from django.test import Client, TestCase

from speakers.services import send_invitation

TINY_JPEG = None


def tiny_jpeg():
    """A 2x2 JPEG, made once, for the ffmpeg stub."""
    global TINY_JPEG
    if TINY_JPEG is None:
        from io import BytesIO

        from PIL import Image

        out = BytesIO()
        Image.new("RGB", (2, 2), "red").save(out, "JPEG")
        TINY_JPEG = out.getvalue()
    return TINY_JPEG


@pytest.fixture(autouse=True)
def ffmpeg(monkeypatch):
    """No test runs ffmpeg unless it asks: a video that becomes READY
    queues a thumbnail (eager in tests), and the stub hands back a tiny
    frame."""
    mock = MagicMock(return_value=tiny_jpeg())
    monkeypatch.setattr("speakers.thumbnails.run_ffmpeg", mock)
    return mock


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """A file attached in the admin is written under ``MEDIA_ROOT``, which
    in CI's container is a bind mount the test user cannot write. Every
    test writes under its own temporary directory instead."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture(autouse=True)
def ffprobe(monkeypatch):
    """No test shells out to ffprobe unless it asks: the probe answers
    120 seconds. A video that becomes READY queues a probe (eager in
    tests), so this keeps every upload test off the real binary."""
    mock = MagicMock(return_value='{"format": {"duration": "120.0"}}')
    monkeypatch.setattr("speakers.probe.run_ffprobe", mock)
    return mock


class CommittingClient(Client):
    """A test client that runs ``transaction.on_commit`` hooks after each
    request, the way a real request's commit would, so a view that queues
    an email leaves it in ``mail.outbox``."""

    def request(self, **request):
        with TestCase.captureOnCommitCallbacks(execute=True):
            return super().request(**request)


@pytest.fixture
def client():
    """Overrides pytest-django's client for the speakers tests."""
    return CommittingClient()


@pytest.fixture
def send(django_capture_on_commit_callbacks):
    """Send an invitation and run the commit hooks, so the email goes out.

    ``send_invitation`` queues the email with ``transaction.on_commit``,
    and a test's transaction never commits. Tests that read the mailbox
    send through this; the rest call ``send_invitation`` directly and just
    get a token.
    """

    def _send(invitation, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            send_invitation(invitation, **kwargs)
        return invitation

    return _send
