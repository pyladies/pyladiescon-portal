"""Signals the speaker portal emits for other stages to hook into."""

from django.dispatch import Signal

# Sent once a presenter has accepted an invitation, with keyword arguments
# ``invitation``, ``presenter`` and ``user``. Stage 2 instantiates the
# presenter's checklist here.
invitation_accepted = Signal()
