from allauth.account.models import EmailAddress
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Exists, OuterRef, Q
from import_export import resources, widgets
from import_export.admin import ImportExportModelAdmin
from import_export.fields import Field

from portal.models import Conference
from volunteer.constants import ApplicationStatus
from volunteer.models import VolunteerProfile

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


# ---- Groups: who is in them, from the group's side -------------------------
#
# Groups are global, not per edition, so membership never expires by itself
# (edition-scoped rights live on teams, design §7.1). The group page shows
# its members with their standing, offers this year's approved volunteers
# as candidates, and lets a stale member be moved out and saved. Speakers
# need no group: the speaker side is relational.


def with_standing(users):
    """Annotate what makes an account a candidate: verified, approved."""
    conference = Conference.get_active()
    approved = VolunteerProfile.objects.filter(
        user_id=OuterRef("pk"), application_status=ApplicationStatus.APPROVED
    )
    if conference is None:
        approved = approved.none()
    else:
        approved = approved.filter(conference=conference)
    return users.annotate(
        verified=Exists(
            EmailAddress.objects.filter(user_id=OuterRef("pk"), verified=True)
        ),
        approved=Exists(approved),
    )


ELIGIBLE = Q(is_active=True, verified=True, approved=True)


class MemberChoiceField(forms.ModelMultipleChoiceField):
    """Members named with their standing, so the chosen box reads as a
    review: who no longer volunteers this year, whose address is unverified."""

    def label_from_instance(self, user):
        label = f"{user.get_full_name() or user.username} ({user.username})"
        if not user.is_active:
            return f"{label}, account inactive"
        if not user.verified:
            return f"{label}, email unverified"
        if not user.approved:
            return f"{label}, not volunteering this year"
        return label


class GroupForm(forms.ModelForm):
    """Django's group form plus the members, as a side-by-side box.

    The candidates are this year's approved volunteers with a verified
    address, plus whoever is already in the group: the widget renders from
    that queryset and the form validates against it, so what is offered and
    what is accepted are one set, and an existing stale member never breaks
    the page when it is saved for another reason.
    """

    users = MemberChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Members",
        widget=FilteredSelectMultiple("members", False),
        help_text=(
            "This year's approved volunteers with a verified email address, and "
            "everyone already in the group. Membership does not expire with the "
            "edition: a member who no longer volunteers stays until moved out, "
            "and the label says so."
        ),
    )

    class Meta:
        model = Group
        fields = ["name", "permissions", "users"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = Q(groups=self.instance) if self.instance.pk else Q(pk__in=[])
        self.fields["users"].queryset = (
            with_standing(User.objects.all())
            .filter(ELIGIBLE | current)
            .order_by("first_name", "last_name", "username")
        )
        if self.instance.pk:
            self.initial["users"] = list(
                self.instance.user_set.values_list("pk", flat=True)
            )


class GroupAdmin(DjangoGroupAdmin):
    """Django's group admin with members on the page and counted on the list."""

    form = GroupForm
    list_display = ("name", "member_count", "stale_member_count")

    def get_queryset(self, request):
        verified = EmailAddress.objects.filter(
            user_id=OuterRef("user__pk"), verified=True
        )
        approved = VolunteerProfile.objects.filter(
            user_id=OuterRef("user__pk"),
            application_status=ApplicationStatus.APPROVED,
            conference=Conference.get_active(),
        )
        stale = Q(user__is_active=False) | ~Exists(verified) | ~Exists(approved)
        return (
            super()
            .get_queryset(request)
            .annotate(
                member_count=Count("user", distinct=True),
                stale_member_count=Count("user", filter=stale, distinct=True),
            )
        )

    @admin.display(description="members", ordering="member_count")
    def member_count(self, group):
        return group.member_count

    @admin.display(
        description="not volunteering this year", ordering="stale_member_count"
    )
    def stale_member_count(self, group):
        return group.stale_member_count

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.user_set.set(form.cleaned_data["users"])


admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)
