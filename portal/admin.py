from django.contrib import admin

from .models import FundraisingGoal


@admin.register(FundraisingGoal)
class FundraisingGoalAdmin(admin.ModelAdmin):
    list_display = ("goal_type", "target_amount", "is_active", "modified_date")
    list_filter = ("goal_type", "is_active")
    search_fields = ("goal_type", "description")
    fields = ("goal_type", "target_amount", "is_active", "description")
    readonly_fields = ("creation_date", "modified_date")

    def get_readonly_fields(self, request, obj=None):
        """Make goal_type readonly after creation to maintain uniqueness."""
        if obj:  # Editing an existing object
            return self.readonly_fields + ("goal_type",)
        return self.readonly_fields
