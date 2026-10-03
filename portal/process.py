"""Which kind of process this is, from how it was started.

Web, the default worker, the media worker and the scheduler share one image and
one set of environment variables, so the environment cannot tell them apart.
What differs is the command line. Sentry events and the worker's startup log
carry the answer, so an error can be traced to the kind of process it came from.
"""

import sys


def process_name(argv=None):
    """``web``, ``worker``, ``worker-media``, ``beat`` or ``other``."""
    argv = list(sys.argv if argv is None else argv)
    command = " ".join(argv)
    if "gunicorn" in command:
        return "web"
    if "celery" not in command:
        return "other"
    if " beat" in command:
        return "beat"
    if " worker" in command:
        queues = ""
        for flag in ("-Q", "--queues"):
            if flag in argv:
                queues = argv[argv.index(flag) + 1]
        return "worker-media" if queues == "media" else "worker"
    return "other"
