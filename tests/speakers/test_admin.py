import pytest
from django.urls import reverse

from .factories import (
    add_presenter,
    make_channel,
    make_presenter,
    make_session,
    make_slot,
)


@pytest.mark.django_db
class TestSpeakersAdmin:
    @pytest.mark.parametrize(
        "model",
        [
            "session",
            "presenter",
            "sessionpresenter",
            "discordchannel",
            "scheduleslot",
            "activitylog",
            "speakersettings",
        ],
    )
    def test_changelists_render(self, client, admin_user, conference, model):
        session = make_session(conference, title="Listed talk")
        presenter = make_presenter(conference, display_name="Listed presenter")
        add_presenter(session, presenter)
        make_slot(session, channel=make_channel(conference))
        client.force_login(admin_user)
        response = client.get(reverse(f"admin:speakers_{model}_changelist"))
        assert response.status_code == 200

    def test_session_change_form_renders_inlines(self, client, admin_user, conference):
        session = make_session(conference)
        add_presenter(session, make_presenter(conference))
        client.force_login(admin_user)
        response = client.get(
            reverse("admin:speakers_session_change", args=[session.pk])
        )
        assert response.status_code == 200
        assert "Session presenters" in response.content.decode()
