from django.contrib import admin, messages

from .models import Conference


@admin.action(description="Clone teams from the previous edition")
def clone_teams_from_previous(modeladmin, request, queryset):
    """Populate each selected edition's teams from the prior year's edition."""
    for target in queryset:
        source = Conference.objects.filter(year=target.year - 1).first()
        if source is None:
            modeladmin.message_user(
                request,
                f"No previous edition found for {target}.",
                level=messages.WARNING,
            )
            continue
        created = target.clone_teams_from(source)
        modeladmin.message_user(
            request,
            f"Cloned {created} team(s) from {source} into {target}.",
            level=messages.SUCCESS,
        )


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ("name", "year", "slug", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
    search_fields = ("name", "year", "slug")
    ordering = ("-year",)
    prepopulated_fields = {"slug": ("name",)}
    actions = [clone_teams_from_previous]
