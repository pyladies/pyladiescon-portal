import json
import logging
import os
import smtplib
import subprocess
import sys
from types import SimpleNamespace

import pytest
from celery.exceptions import Retry, SoftTimeLimitExceeded

from common.tasks import EMAIL_TASK_OPTIONS, email_task, log_worker_ready
from common.workers import email_code_version
from portal.process import process_name
from speakers import tasks as speaker_tasks

attempts = []


@email_task()
def sample_email_task(outcomes):
    """Raises each exception in ``outcomes`` in turn, then succeeds."""
    attempts.append(len(attempts))
    if len(attempts) <= len(outcomes):
        raise outcomes[len(attempts) - 1]
    return "sent"


@pytest.fixture(autouse=True)
def fresh_attempts():
    attempts.clear()


class TestEmailTaskOptions:
    def test_a_killed_worker_gives_the_task_back(self):
        assert sample_email_task.acks_late is True
        assert sample_email_task.reject_on_worker_lost is True

    def test_it_is_bounded_in_time_and_in_tries(self):
        assert sample_email_task.max_retries == 4
        assert sample_email_task.soft_time_limit < sample_email_task.time_limit
        assert sample_email_task.time_limit == 120

    def test_options_can_be_overridden(self):
        @email_task(max_retries=1, bind=True)
        def other(self):
            return self.max_retries

        assert other.max_retries == 1
        assert other.apply().result == 1
        assert EMAIL_TASK_OPTIONS["max_retries"] == 4

    def test_smtp_errors_are_oserrors_so_refusals_are_excluded_by_name(self):
        """``SMTPException`` is an ``OSError``: retrying on ``OSError`` alone
        would also retry an address the server refused."""
        assert issubclass(smtplib.SMTPRecipientsRefused, OSError)
        excluded = EMAIL_TASK_OPTIONS["dont_autoretry_for"]
        for refusal in (
            smtplib.SMTPRecipientsRefused,
            smtplib.SMTPSenderRefused,
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPNotSupportedError,
        ):
            assert issubclass(refusal, excluded)


class TestRetries:
    """In tests tasks run eagerly and a requested retry is raised as ``Retry``
    rather than run again, so these assert what the task asks for."""

    @pytest.mark.parametrize(
        "error",
        [
            ConnectionError("reset"),
            TimeoutError("slow"),
            smtplib.SMTPServerDisconnected("gone"),
            SoftTimeLimitExceeded(),
        ],
    )
    def test_a_server_that_is_down_or_slow_is_tried_again(self, error):
        with pytest.raises(Retry):
            sample_email_task.apply(args=[[error]])
        assert len(attempts) == 1

    def test_a_later_try_can_succeed(self):
        with pytest.raises(Retry):
            sample_email_task.apply(args=[[ConnectionError("down")]])
        result = sample_email_task.apply(args=[[ConnectionError("down")]], retries=1)
        assert result.result == "sent"

    def test_the_last_try_raises_the_real_error(self):
        errors = [ConnectionError("down")] * 2
        attempts.append("earlier")
        with pytest.raises(ConnectionError):
            sample_email_task.apply(
                args=[errors], retries=sample_email_task.max_retries
            )

    @pytest.mark.parametrize(
        "error",
        [
            smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")}),
            smtplib.SMTPSenderRefused(553, b"bad sender", "x@example.com"),
            smtplib.SMTPAuthenticationError(535, b"bad login"),
        ],
    )
    def test_a_refusal_is_not_tried_again(self, error):
        with pytest.raises(smtplib.SMTPException):
            sample_email_task.apply(args=[[error]])
        assert len(attempts) == 1


class TestWhichTasksAreCovered:
    COVERED = (
        speaker_tasks.send_invitation_email_task,
        speaker_tasks.send_added_to_session_email_task,
        speaker_tasks.send_acceptance_email_task,
        speaker_tasks.send_proposal_approved_email_task,
        speaker_tasks.send_proposal_rejected_email_task,
    )
    LEFT_ALONE = (
        speaker_tasks.send_proposal_received_email_task,
        speaker_tasks.send_copresenter_suggestion_task,
        speaker_tasks.send_checklist_digests_task,
        speaker_tasks.send_checklist_change_notices_task,
    )

    def test_one_recipient_email_tasks_are_covered(self):
        for task in self.COVERED:
            assert task.acks_late is True, task.name
            assert task.reject_on_worker_lost is True, task.name
            assert task.max_retries == 4, task.name

    def test_tasks_that_send_to_several_people_are_not(self):
        """A retry would send again to those who already have it."""
        for task in self.LEFT_ALONE:
            assert not task.acks_late, task.name
            assert not getattr(task, "autoretry_for", None), task.name


class TestWorkerReady:
    def test_logs_which_process_and_which_code(self, caplog):
        with caplog.at_level(logging.INFO, logger="common.tasks"):
            log_worker_ready(sender=SimpleNamespace(hostname="celery@worker-1"))
        assert "Worker ready: celery@worker-1" in caplog.text
        assert f"email_code={email_code_version()}" in caplog.text
        assert "process=" in caplog.text

    def test_a_sender_without_a_hostname_still_logs(self, caplog):
        with caplog.at_level(logging.INFO, logger="common.tasks"):
            log_worker_ready()
        assert "Worker ready: ?" in caplog.text


class TestProcessName:
    @pytest.mark.parametrize(
        "argv, expected",
        [
            (["/usr/bin/gunicorn", "-c", "config/gunicorn.conf.py", "x:app"], "web"),
            (["celery", "-A", "portal", "worker", "--loglevel=info"], "worker"),
            (["celery", "-A", "portal", "worker", "-Q", "media"], "worker-media"),
            (["celery", "-A", "portal", "worker", "--queues=media"], "worker-media"),
            (["celery", "-A", "portal", "worker", "--queues", "media"], "worker-media"),
            (["celery", "-A", "portal", "worker", "-Q", "celery,media"], "worker"),
            (["celery", "-A", "portal", "worker", "-Q", "media,celery"], "worker"),
            (["celery", "-A", "portal", "worker", "-Q"], "worker"),
            (["celery", "-A", "portal", "beat"], "beat"),
            (["celery", "-A", "portal", "inspect", "ping"], "other"),
            (["manage.py", "shell"], "other"),
            ([], "other"),
        ],
    )
    def test_from_the_command_line(self, argv, expected):
        assert process_name(argv) == expected

    def test_defaults_to_this_process(self):
        assert process_name() == process_name(sys.argv)


def settings_in_a_fresh_interpreter(**env):
    """``portal.settings`` as a process started with ``env`` would see it.
    The module is imported once and is not measured, so it is read in a
    process of its own."""
    code = (
        "import json; from django.conf import settings as s;"
        "print(json.dumps({k: getattr(s, k, None) for k in ("
        "'EMAIL_TIMEOUT','EMAIL_HOST_PASSWORD','CELERY_WORKER_CONCURRENCY',"
        "'CELERY_WORKER_PREFETCH_MULTIPLIER','CELERY_BROKER_TRANSPORT_OPTIONS')}))"
    )
    base = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_EMAIL")}
    base.pop("CELERY_WORKER_CONCURRENCY", None)
    base["DJANGO_SETTINGS_MODULE"] = "portal.settings"
    done = subprocess.run(
        [sys.executable, "-c", code],
        env={**base, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestSettings:
    SMTP = {"DJANGO_EMAIL_HOST": "smtp.example.com"}

    def test_a_mail_server_that_goes_quiet_does_not_hold_a_process(self):
        assert settings_in_a_fresh_interpreter(**self.SMTP)["EMAIL_TIMEOUT"] == 30

    def test_the_timeout_can_be_set(self):
        env = {**self.SMTP, "DJANGO_EMAIL_TIMEOUT": "10"}
        assert settings_in_a_fresh_interpreter(**env)["EMAIL_TIMEOUT"] == 10

    def test_the_password_is_read_under_either_name(self):
        misspelt = {**self.SMTP, "DJANOG_EMAIL_HOST_PASSWORD": "old"}
        assert (
            settings_in_a_fresh_interpreter(**misspelt)["EMAIL_HOST_PASSWORD"] == "old"
        )
        both = {**misspelt, "DJANGO_EMAIL_HOST_PASSWORD": "new"}
        assert settings_in_a_fresh_interpreter(**both)["EMAIL_HOST_PASSWORD"] == "new"

    def test_workers_are_few_by_default_and_hold_one_task_each(self):
        found = settings_in_a_fresh_interpreter()
        assert found["CELERY_WORKER_CONCURRENCY"] == 2
        assert found["CELERY_WORKER_PREFETCH_MULTIPLIER"] == 1

    def test_concurrency_can_be_set(self):
        found = settings_in_a_fresh_interpreter(CELERY_WORKER_CONCURRENCY="4")
        assert found["CELERY_WORKER_CONCURRENCY"] == 4

    def test_the_broker_connection_is_bounded_and_kept_alive(self):
        options = settings_in_a_fresh_interpreter()["CELERY_BROKER_TRANSPORT_OPTIONS"]
        assert options["socket_connect_timeout"] == 5
        assert options["socket_keepalive"] is True
        assert options["health_check_interval"] == 30
