"""Signals the speaker portal emits for other stages to hook into."""

from django.dispatch import Signal

# Sent once a presenter has accepted an invitation, with keyword arguments
# ``invitation``, ``presenter``, ``user`` and ``session_presenters`` (the
# SessionPresenter rows confirmed by this acceptance). The presenter's
# checklists are instantiated here (speakers/receivers.py).
invitation_accepted = Signal()

# Sent by ``Session.confirm()`` after the status is saved, with ``session``.
# The session-scope checklist (post-production) is instantiated here.
session_confirmed = Signal()
