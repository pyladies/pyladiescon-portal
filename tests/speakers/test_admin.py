import pytest
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.forms import modelform_factory
from django.urls import reverse

from speakers.checklists import add_adhoc_item
from speakers.constants import ItemOwner

from .factories import (
    add_presenter,
    make_channel,
    make_presenter,
    make_proposal,
    make_session,
    make_settings,
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
            "proposal",
            "readinessgate",
            "handbookreadreceipt",
        ],
    )
    def test_changelists_render(self, client, admin_user, conference, model):
        session = make_session(conference, title="Listed talk")
        presenter = make_presenter(conference, display_name="Listed presenter")
        add_presenter(session, presenter)
        make_slot(session, channel=make_channel(conference))
        make_proposal(session, presenter)
        client.force_login(admin_user)
        response = client.get(reverse(f"admin:speakers_{model}_changelist"))
        assert response.status_code == 200

    def test_checklist_item_status_is_read_only(self, client, admin_user, conference):
        """Status changes go through the service, which logs them and
        refuses to hand-tick automatic items; the admin only shows them."""
        item = add_adhoc_item(
            conference,
            "Sign the form",
            ItemOwner.SPEAKER,
            presenter=make_presenter(conference),
        )
        client.force_login(admin_user)
        response = client.get(
            reverse("admin:speakers_checklistitem_change", args=[item.pk])
        )
        content = response.content.decode()
        assert response.status_code == 200
        assert 'name="status"' not in content
        assert 'name="note"' not in content
        assert 'name="assignee"' in content

    def test_settings_form_offers_the_proposals_switch(
        self, client, admin_user, conference
    ):
        """The switch defaults to off and nothing else in the portal sets
        it, so the admin form is where an organizer opens proposals; the
        first edition shipped without the field on the form."""
        row = make_settings(conference)
        client.force_login(admin_user)
        url = reverse("admin:speakers_speakersettings_change", args=[row.pk])
        content = client.get(url).content.decode()
        assert 'name="proposals_open"' in content
        assert 'name="proposals_intro_md"' in content

    def test_pinned_admin_forms_offer_every_editable_field(self):
        """A pinned fieldset drops a field added later without a word: the
        proposals switch shipped unreachable that way. Every editable
        field is on the form, read-only on it, or named in ``exclude``."""
        for model, model_admin in admin.site._registry.items():
            # ``fields`` pins the form the same way; no speakers admin uses
            # it today, so it is folded in rather than given a branch.
            pinned = model_admin.fieldsets or (
                model_admin.fields and [(None, {"fields": model_admin.fields})]
            )
            if model._meta.app_label != "speakers" or not pinned:
                continue
            shown = set(flatten_fieldsets(pinned))
            editable = set(
                modelform_factory(
                    model, form=model_admin.form, fields="__all__"
                ).base_fields
            )
            allowed = (
                shown
                | set(model_admin.readonly_fields)
                | set(model_admin.exclude or ())
            )
            assert editable <= allowed, (model.__name__, sorted(editable - allowed))

    def test_session_change_form_renders_inlines(self, client, admin_user, conference):
        session = make_session(conference)
        add_presenter(session, make_presenter(conference))
        client.force_login(admin_user)
        response = client.get(
            reverse("admin:speakers_session_change", args=[session.pk])
        )
        assert response.status_code == 200
        assert "Session presenters" in response.content.decode()
