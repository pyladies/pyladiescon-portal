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
    ScheduleSlot,
    Session,
    SessionPresenter,
    SessionType,
    SpeakerSettings,
)


@admin.register(SpeakerSettings)
class SpeakerSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "conference",
        "speaker_module_enabled",
        "default_premiere_location",
        "translation_languages",
    )
    list_filter = ("speaker_module_enabled",)
    list_select_related = ("conference",)


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
    readonly_fields = ("completed_by", "completed_at")


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
    list_display = ("title", "version", "published_at", "conference")
    list_filter = (ActiveConferenceFilter,)
    list_select_related = ("conference",)
    inlines = [HandbookReadReceiptInline]
