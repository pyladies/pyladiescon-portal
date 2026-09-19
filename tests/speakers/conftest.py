"""Fixtures shared by the speakers tests."""

import pytest

from speakers.services import send_invitation


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
