from django.contrib.auth.mixins import UserPassesTestMixin


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin for views that require administrative permission.

    Currently it requires the user to be a superuser or staff member.
    This can be extended to include more complex permission checks in the future.
    """

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.is_staff
