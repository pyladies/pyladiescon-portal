from django.contrib import admin

from portal.admin_filters import ActiveConferenceFilter

from .models import (
    ActivityLog,
    DiscordChannel,
    Presenter,
    ScheduleSlot,
    Session,
    SessionPresenter,
    SpeakerSettings,
)


@admin.register(SpeakerSettings)
class SpeakerSettingsAdmin(admin.ModelAdmin):
    list_display = ("conference", "speaker_module_enabled", "default_premiere_location")
    list_filter = ("speaker_module_enabled",)
    list_select_related = ("conference",)


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
    list_select_related = ("conference",)
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
    autocomplete_fields = ("user", "liaison")
    prepopulated_fields = {"slug": ("display_name",)}


@admin.register(SessionPresenter)
class SessionPresenterAdmin(admin.ModelAdmin):
    list_display = ("presenter", "session", "role", "order", "confirmed_at")
    list_filter = (ActiveConferenceFilter, "role")
    list_select_related = ("presenter", "session", "conference")
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
