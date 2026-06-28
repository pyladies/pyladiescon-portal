from django.contrib.auth.mixins import UserPassesTestMixin

from volunteer.models import Team, VolunteerProfile


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require administrative permission.

    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff


class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin for views restricted to superusers only (not staff)."""

    def test_func(self):
        return self.request.user.is_superuser


class VolunteerOrAdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require the user to be the owner of the object or an admin.

    This is useful for views where users can only access their own data unless they have
    administrative privileges.
    """

    def test_func(self):
        pk = self.kwargs.get("pk")
        instance = VolunteerProfile.objects.filter(pk=pk).first()
        is_owner = False
        if instance and instance.user == self.request.user:
            is_owner = True
        is_admin = self.request.user.is_superuser or self.request.user.is_staff
        return is_owner or is_admin


class TeamLeadRequiredMixin(UserPassesTestMixin):
    """Mixin for views scoped to a single team in the URL (``pk``).

    Access is granted to admins (superuser or staff) and to volunteers who are
    a lead of *that* team. This mirrors ``CanViewSponsorship`` scoping its
    access to the conferences a viewer is allowed to see: a team lead only
    reaches the teams they actually lead, never every team.
    """

    def get_team(self):
        return Team.objects.filter(pk=self.kwargs.get("pk")).first()

    def is_team_lead(self, team):
        if team is None:
            return False
        return team.team_leads.filter(user=self.request.user).exists()

    def test_func(self):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return True
        return self.is_team_lead(self.get_team())
