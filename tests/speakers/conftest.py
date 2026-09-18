"""Fixtures shared by the speakers tests."""

import pytest
from django.db import transaction

# Kept so a test can restore it and watch the real commit hook.
REAL_ON_COMMIT = transaction.on_commit


@pytest.fixture(autouse=True)
def run_on_commit_now(monkeypatch):
    """Run ``transaction.on_commit`` callbacks immediately.

    Tests run inside a transaction that never commits, so callbacks the
    services register (queueing the invitation email, for one) would never
    fire and every "the email was sent" assertion would fail. Tests about
    the commit hook itself restore ``REAL_ON_COMMIT``.
    """
    monkeypatch.setattr(
        transaction, "on_commit", lambda func, using=None, robust=False: func()
    )
