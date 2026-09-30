from allauth.account.models import EmailAddress
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Count, Exists, OuterRef, Q
from django.utils.html import format_html, format_html_join
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


def approved_this_year(user_ref):
    """The approved volunteer profiles of the active edition for the user
    at ``user_ref``, and none at all when no edition is active: the one
    spelling of "volunteering this year" that the form and the list share."""
    profiles = VolunteerProfile.objects.filter(
        user_id=OuterRef(user_ref), application_status=ApplicationStatus.APPROVED
    )
    conference = Conference.get_active()
    if conference is None:
        return profiles.none()
    return profiles.filter(conference=conference)


def with_standing(users):
    """Annotate what makes an account a candidate: verified, approved."""
    return users.annotate(
        verified=Exists(
            EmailAddress.objects.filter(user_id=OuterRef("pk"), verified=True)
        ),
        approved=Exists(approved_this_year("pk")),
    )


ELIGIBLE = Q(is_active=True, verified=True, approved=True)


def standing_label(user):
    """A member's name with their standing, so a roster reads as a review:
    who no longer volunteers this year, whose address is unverified."""
    label = f"{user.get_full_name() or user.username} ({user.username})"
    if not user.is_active:
        return f"{label}, account inactive"
    if not user.verified:
        return f"{label}, email unverified"
    if not user.approved:
        return f"{label}, not volunteering this year"
    return label


class MemberChoiceField(forms.ModelMultipleChoiceField):
    """Members named with their standing (``standing_label``)."""

    def label_from_instance(self, user):
        return standing_label(user)


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
        # ``groups=`` joins every group row a user has, and ORed with the
        # eligibility test each of those rows matches, so a volunteer in
        # three other groups came out three times: distinct, as the
        # organizer-side candidates do (speakers/people.py).
        self.fields["users"].queryset = (
            with_standing(User.objects.all())
            .filter(ELIGIBLE | current)
            .order_by("first_name", "last_name", "username")
            .distinct()
        )
        if self.instance.pk:
            self.initial["users"] = list(
                self.instance.user_set.values_list("pk", flat=True)
            )


class GroupAdmin(DjangoGroupAdmin):
    """Django's group admin with members on the page and counted on the list."""

    form = GroupForm
    list_display = ("name", "member_count", "stale_member_count")

    # Someone who may view groups but not change them gets the roster as a
    # read-only list: ``users`` is a form field, not a model field, so
    # Django's read-only path has nothing to render it from, and the
    # section would otherwise be silently absent.
    def get_readonly_fields(self, request, obj=None):
        if obj is not None and not self.has_change_permission(request, obj):
            return ("members",)
        return super().get_readonly_fields(request, obj)

    def get_fields(self, request, obj=None):
        if obj is not None and not self.has_change_permission(request, obj):
            return ["name", "permissions", "members"]
        return super().get_fields(request, obj)

    @admin.display(description="members")
    def members(self, group):
        users = with_standing(group.user_set.all()).order_by(
            "first_name", "last_name", "username"
        )
        if not users:
            return "Nobody."
        return format_html(
            "<ul>{}</ul>",
            format_html_join("", "<li>{}</li>", ((standing_label(u),) for u in users)),
        )

    def get_queryset(self, request):
        verified = EmailAddress.objects.filter(
            user_id=OuterRef("user__pk"), verified=True
        )
        approved = approved_this_year("user__pk")
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
