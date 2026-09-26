from django import forms
from django.contrib import admin

from portal.admin_filters import ActiveConferenceFilter

from .models import (
    ActivityLog,
    ChecklistItem,
    ChecklistTemplate,
    ChecklistTemplateItem,
    DiscordChannel,
    Handbook,
    HandbookReadReceipt,
    Invitation,
    MediaAsset,
    Presenter,
    PresenterRole,
    Proposal,
    ReadinessGate,
    ReminderLog,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)


class SpeakerSettingsAdminForm(forms.ModelForm):
    """The token and the webhook secret are write-only here: encrypted at
    rest, never echoed back to the page. Leave a field blank to keep what is
    stored; a stored value this deploy cannot decrypt is kept as is."""

    pretix_api_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current token.",
    )
    pretix_webhook_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leave blank to keep the current secret.",
    )

    class Meta:
        model = SpeakerSettings
        fields = "__all__"

    def _keep_when_blank(self, name):
        value = self.cleaned_data.get(name)
        return value if value else getattr(self.instance, name)

    def clean_pretix_api_token(self):
        return self._keep_when_blank("pretix_api_token")

    def clean_pretix_webhook_secret(self):
        return self._keep_when_blank("pretix_webhook_secret")


@admin.register(SpeakerSettings)
class SpeakerSettingsAdmin(admin.ModelAdmin):
    form = SpeakerSettingsAdminForm
    list_display = (
        "conference",
        "speaker_module_enabled",
        "proposals_open",
        "default_premiere_location",
        "translation_languages",
        "pretix_organizer",
        "pretix_last_synced_at",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "conference",
                    "speaker_module_enabled",
                    "conference_timezone",
                    "organizers_email",
                )
            },
        ),
        (
            "Program",
            {
                "fields": (
                    "default_premiere_location",
                    "translation_languages",
                    "default_video_length_limit_minutes",
                )
            },
        ),
        (
            "Proposals",
            {
                "description": "While proposals are open, the landing page and the "
                "hubs offer the propose-a-session form to anyone with an account. "
                "Only session types marked open for proposals are offered.",
                "fields": ("proposals_open", "proposals_intro_md"),
            },
        ),
        (
            "Pretix",
            {
                "description": "Token and webhook secret are encrypted at rest and "
                "never shown again; leave blank to keep the stored value.",
                "fields": (
                    "pretix_base_url",
                    "pretix_organizer",
                    "pretix_event",
                    "pretix_api_token",
                    "pretix_webhook_secret",
                    "pretix_last_synced_at",
                ),
            },
        ),
    )
    list_filter = ("speaker_module_enabled", "proposals_open")
    list_select_related = ("conference",)
    # Written by the nightly reconciliation, which pages from it; a hand
    # edit would move that window.
    readonly_fields = ("pretix_last_synced_at",)
    # Voucher creation is not built (pretix.create_voucher raises while the
    # switch is on), so the switch stays off the form until it is. Named
    # here rather than dropped from the fieldsets in silence: the admin
    # tests check that every editable field is offered or excluded.
    exclude = ("pretix_create_vouchers",)


@admin.register(PresenterRole)
class PresenterRoleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "email_word",
        "sort_order",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_active")
    search_fields = ("name", "code")
    list_select_related = ("conference",)


@admin.register(SessionType)
class SessionTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "is_content",
        "default_duration_minutes",
        "default_delivery",
        "sort_order",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_content", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("conference",)
    filter_horizontal = ("roles",)


class SessionPresenterInline(admin.TabularInline):
    model = SessionPresenter
    extra = 0
    fields = ("presenter", "role", "order", "confirmed_at")
    autocomplete_fields = ("presenter",)


class ScheduleSlotInline(admin.StackedInline):
    model = ScheduleSlot
    extra = 0
    fields = ("channel", "start_utc", "end_utc")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "delivery", "status", "is_public", "conference")
    list_filter = (ActiveConferenceFilter, "kind", "delivery", "status", "is_public")
    search_fields = ("title", "slug")
    list_select_related = ("conference", "kind")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [SessionPresenterInline, ScheduleSlotInline]


@admin.register(Presenter)
class PresenterAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "email",
        "user",
        "liaison",
        "is_public",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "is_public")
    search_fields = ("display_name", "email", "slug")
    list_select_related = ("conference", "user", "liaison")
    autocomplete_fields = ("user", "liaison", "pretix_order")
    prepopulated_fields = {"slug": ("display_name",)}


@admin.register(SessionPresenter)
class SessionPresenterAdmin(admin.ModelAdmin):
    list_display = ("presenter", "session", "role", "order", "confirmed_at")
    list_filter = (ActiveConferenceFilter, "role")
    list_select_related = ("presenter", "session", "role", "conference")
    autocomplete_fields = ("session", "presenter")


@admin.register(DiscordChannel)
class DiscordChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "channel_id", "is_active", "conference")
    list_filter = (ActiveConferenceFilter, "kind", "is_active")
    search_fields = ("name", "channel_id")
    list_select_related = ("conference",)


@admin.register(ScheduleSlot)
class ScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ("session", "channel", "start_utc", "end_utc", "conference")
    list_filter = (ActiveConferenceFilter, "channel")
    list_select_related = ("session", "channel", "conference")
    autocomplete_fields = ("session",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("creation_date", "action", "actor", "target", "conference")
    list_filter = (ActiveConferenceFilter, "action")
    list_select_related = ("actor", "conference", "content_type")
    readonly_fields = ("creation_date", "modified_date", "target")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "presenter",
        "session",
        "status",
        "sent_at",
        "opened_at",
        "accepted_at",
        "declined_at",
        "conference",
    )
    list_filter = (ActiveConferenceFilter,)
    search_fields = ("presenter__display_name", "presenter__email", "session__title")
    list_select_related = ("presenter", "session", "conference")
    autocomplete_fields = ("presenter", "session", "invited_by")
    readonly_fields = (
        "token",
        "sent_at",
        "expires_at",
        "opened_at",
        "accepted_at",
        "declined_at",
        "cancelled_at",
    )


class ChecklistTemplateItemInline(admin.TabularInline):
    model = ChecklistTemplateItem
    extra = 0
    fields = (
        "order",
        "owner",
        "title",
        "due_anchor",
        "due_offset_days",
        "auto_complete_rule",
        "requires_asset_kind",
        "requires_asset_language",
        "requires_handbook",
        "per_translation_language",
        "is_required",
        "assignee_default",
    )


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "scope",
        "kind",
        "role",
        "delivery",
        "is_active",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "scope", "kind", "is_active")
    search_fields = ("name",)
    list_select_related = ("conference",)
    inlines = [ChecklistTemplateItemInline]


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "status",
        "presenter",
        "session",
        "due_date",
        "assignee",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "owner", "status", "is_required")
    search_fields = ("title", "presenter__display_name", "session__title")
    list_select_related = ("presenter", "session", "assignee", "conference")
    autocomplete_fields = ("presenter", "session", "assignee", "template_item")
    # Status changes go through ``speakers.checklists.set_item_status`` (the
    # organizer views), which logs them, refuses to hand-tick automatic items
    # and re-tries the session's confirmation. The admin is for looking.
    readonly_fields = ("status", "note", "completed_by", "completed_at")


@admin.register(ChecklistTemplateItem)
class ChecklistTemplateItemAdmin(admin.ModelAdmin):
    """Registered so it can be an autocomplete target; edit items inline on
    the template instead."""

    list_display = ("title", "template", "owner", "order")
    search_fields = ("title", "template__name")
    list_select_related = ("template",)


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "kind",
        "language",
        "version",
        "status",
        "duration_seconds",
        "conference",
    )
    list_filter = (ActiveConferenceFilter, "kind", "status")
    search_fields = ("session__title",)
    list_select_related = ("session", "conference")
    autocomplete_fields = ("session", "uploaded_by")


class HandbookReadReceiptInline(admin.TabularInline):
    model = HandbookReadReceipt
    extra = 0
    fields = ("presenter", "read_at")
    readonly_fields = ("read_at",)
    autocomplete_fields = ("presenter",)


@admin.register(Handbook)
class HandbookAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "version", "published_at", "conference")
    list_filter = (ActiveConferenceFilter, "key")
    list_select_related = ("conference",)
    inlines = [HandbookReadReceiptInline]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("item", "threshold_days", "recipient", "sent_at", "conference")
    list_filter = (ActiveConferenceFilter, "threshold_days")
    search_fields = ("recipient", "item__title")
    list_select_related = ("item", "conference")
    readonly_fields = ("sent_at",)


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("session", "presenter", "decision", "submitted_at", "conference")
    list_filter = (ActiveConferenceFilter, "decision")
    search_fields = ("session__title", "presenter__display_name")
    list_select_related = ("session", "presenter", "conference")
    readonly_fields = ("conference", "submitted_at", "decided_at")


@admin.register(ReadinessGate)
class ReadinessGateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_open", "opened_at", "conference")
    list_filter = (ActiveConferenceFilter, "is_open")
    search_fields = ("code", "name")
    list_select_related = ("conference",)
    readonly_fields = ("opened_at", "opened_by")


@admin.register(HandbookReadReceipt)
class HandbookReadReceiptAdmin(admin.ModelAdmin):
    list_display = ("handbook", "presenter", "read_at", "conference")
    list_filter = (ActiveConferenceFilter,)
    search_fields = ("presenter__display_name", "handbook__title")
    list_select_related = ("handbook", "presenter", "conference")
    readonly_fields = ("read_at",)
