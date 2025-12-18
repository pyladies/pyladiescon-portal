import pytest
from portal.celery import debug_task


def test_debug_task(capsys):
    """Test the debug task execution."""
    debug_task()

    captured = capsys.readouterr()
    assert 'Request:' in captured.out