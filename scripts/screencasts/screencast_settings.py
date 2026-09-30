"""Settings for the screencast server: the portal's own, with Celery eager.

The project only runs tasks eagerly under pytest, and a plain runserver has no
broker, so without this the invitation and proposal emails would never send.
"""

from portal.settings import *  # noqa: F401,F403

CELERY_TASK_ALWAYS_EAGER = True
