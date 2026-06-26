from celery import shared_task

from .models import (
    Role,
    Team,
    VolunteerProfile,
    send_internal_notification_email,
    send_internal_volunteer_onboarding_email,
    send_volunteer_cancelled_emails,
    send_volunteer_notification_email,
    send_volunteer_onboarding_email,
)


def _get_profile(profile_id):
    try:
        return VolunteerProfile.objects.get(id=profile_id)
    except VolunteerProfile.DoesNotExist:
        return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_volunteer_profile_emails_task(self, profile_id, created):
    """Notify the applicant (and the internal team on creation) when a
    volunteer profile is created or updated."""
    profile = _get_profile(profile_id)
    if profile is None:
        return f"VolunteerProfile with id {profile_id} not found"
    if created:
        send_internal_notification_email(profile)
        send_volunteer_notification_email(profile)
    else:
        send_volunteer_notification_email(profile, updated=True)
    return f"Sent volunteer profile emails for {profile_id}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_volunteer_onboarding_email_task(self, profile_id):
    """Send the onboarding email to an approved volunteer."""
    profile = _get_profile(profile_id)
    if profile is None:
        return f"VolunteerProfile with id {profile_id} not found"
    send_volunteer_onboarding_email(profile)
    return f"Sent volunteer onboarding email for {profile_id}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_internal_volunteer_onboarding_email_task(self, profile_id):
    """Notify the internal team to complete onboarding for an approved
    volunteer."""
    profile = _get_profile(profile_id)
    if profile is None:
        return f"VolunteerProfile with id {profile_id} not found"
    send_internal_volunteer_onboarding_email(profile)
    return f"Sent internal volunteer onboarding email for {profile_id}"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_volunteer_cancelled_emails_task(self, profile_id, team_ids, role_ids):
    """Notify the volunteer and affected team leads about a cancellation.

    The teams/roles were removed from the profile before this runs, but the
    Team/Role rows persist, so they are re-fetched by id.
    """
    profile = _get_profile(profile_id)
    if profile is None:
        return f"VolunteerProfile with id {profile_id} not found"
    teams = list(Team.objects.filter(id__in=team_ids))
    roles = list(Role.objects.filter(id__in=role_ids))
    send_volunteer_cancelled_emails(profile, teams, roles)
    return f"Sent volunteer cancellation emails for {profile_id}"
