from allauth.account.models import EmailAddress
from django.contrib import admin
from django.db.models import Exists, OuterRef
from import_export import resources, widgets
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from .models import PortalProfile


def with_account_context(queryset):
    """Add the account columns the changelist and the export both need.

    ``email_verified`` answers "did this account ever confirm an address",
    which is what separates a real sign-up from a drive-by one. Annotating it
    keeps that one query instead of one per row.
    """
    return queryset.select_related("user").annotate(
        email_verified=Exists(
            EmailAddress.objects.filter(user_id=OuterRef("user_id"), verified=True)
        )
    )


class PortalProfileResource(resources.ModelResource):
    """Export profiles together with the account context needed to audit them."""

    # Annotated, not a model field, so it is declared explicitly and never
    # written back on import.
    email_verified = Field(
        attribute="email_verified",
        column_name="email_verified",
        widget=widgets.BooleanWidget(),
        readonly=True,
    )

    def get_queryset(self):
        return with_account_context(super().get_queryset())

    class Meta:
        model = PortalProfile
        fields = (
            "id",
            "user",
            "user__username",
            "user__email",
            "user__first_name",
            "user__last_name",
            "user__date_joined",
            "user__last_login",
            "user__is_active",
            "email_verified",
            "pronouns",
            "coc_agreement",
            "tos_agreement",
            "creation_date",
            "modified_date",
        )
        export_order = fields


class PortalProfileAdmin(ImportExportModelAdmin):
    list_display = (
        "user",
        "user__first_name",
        "user__last_name",
        "user__email",
        "email_verified",
        "pronouns",
        "coc_agreement",
        "tos_agreement",
        "creation_date",
        "modified_date",
    )
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("pronouns", "coc_agreement", "tos_agreement", "creation_date")
    readonly_fields = ("coc_agreement", "tos_agreement")
    # Newest first, with a drill-down by date, so a burst of sign-ups is
    # visible on the changelist rather than having to be searched for.
    ordering = ("-creation_date",)
    date_hierarchy = "creation_date"
    resource_classes = [PortalProfileResource]

    def get_queryset(self, request):
        return with_account_context(super().get_queryset(request))

    @admin.display(
        boolean=True, description="Email verified", ordering="email_verified"
    )
    def email_verified(self, obj):
        """Whether this account has ever confirmed an email address."""
        return obj.email_verified


admin.site.register(PortalProfile, PortalProfileAdmin)
