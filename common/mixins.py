from django.contrib.auth.mixins import UserPassesTestMixin

from volunteer.models import VolunteerProfile


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require administrative permission.

    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff


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
