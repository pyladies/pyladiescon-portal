"""Fixtures shared by the speakers tests."""

from unittest.mock import MagicMock

import pytest
from django.test import Client, TestCase

from speakers.services import send_invitation


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
