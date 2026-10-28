"""Settings for the screencast server: the portal's own, with Celery eager.

The project only runs tasks eagerly under pytest, and a plain runserver has no
broker, so without this the invitation and proposal emails would never send.
"""

import os

from portal.settings import *  # noqa: F401,F403

CELERY_TASK_ALWAYS_EAGER = True

# Files the takes upload or the seeds create (headshots, for one) go under
# scripts/screencasts/out/ with everything else a take leaves behind, not in
# the checkout's media/ folder that the development server serves.
MEDIA_ROOT = os.environ.get("SCREENCAST_MEDIA_ROOT", MEDIA_ROOT)  # noqa: F405
