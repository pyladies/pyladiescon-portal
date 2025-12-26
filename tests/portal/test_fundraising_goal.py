import pytest
from django.contrib.admin.sites import AdminSite

from portal.admin import FundraisingGoalAdmin
from portal.models import FundraisingGoal


@pytest.mark.django_db
class TestFundraisingGoalAdmin:
    def test_fundraising_goal_admin_list_display(self):
        """Test that the admin list display is configured correctly."""
        admin = FundraisingGoalAdmin(FundraisingGoal, AdminSite())
        assert "goal_type" in admin.list_display
        assert "target_amount" in admin.list_display
        assert "is_active" in admin.list_display
        assert "modified_date" in admin.list_display

    def test_fundraising_goal_admin_readonly_fields(self):
        """Test that readonly fields are set correctly on edit."""
        admin = FundraisingGoalAdmin(FundraisingGoal, AdminSite())
        goal = FundraisingGoal.objects.create(
            goal_type="donation", target_amount=2500, is_active=True
        )

        # When editing, goal_type should be readonly
        readonly_fields = admin.get_readonly_fields(None, obj=goal)
        assert "goal_type" in readonly_fields
        assert "creation_date" in readonly_fields
        assert "modified_date" in readonly_fields

        # When creating, only creation_date and modified_date should be readonly
        readonly_fields = admin.get_readonly_fields(None, obj=None)
        assert "goal_type" not in readonly_fields
        assert "creation_date" in readonly_fields
        assert "modified_date" in readonly_fields


@pytest.mark.django_db
class TestFundraisingGoalModel:
    def test_fundraising_goal_str(self):
        """Test the string representation of FundraisingGoal."""
        # First, delete any existing donation goals to avoid unique constraint violation
        FundraisingGoal.objects.filter(goal_type="donation").delete()

        goal = FundraisingGoal.objects.create(
            goal_type="donation",
            target_amount=2500.00,
            is_active=True,
            description="Test donation goal",
        )
        # The decimal might display as $2500.0 or $2500.00 depending on the decimal handling
        assert "Donation Goal: $2500" in str(goal)

    def test_fundraising_goal_unique_goal_type(self):
        """Test that goal_type is unique."""
        # Clean up first
        FundraisingGoal.objects.filter(goal_type="donation").delete()

        FundraisingGoal.objects.create(
            goal_type="donation", target_amount=2500, is_active=True
        )

        # Attempting to create another donation goal should raise an error
        with pytest.raises(Exception):
            FundraisingGoal.objects.create(
                goal_type="donation", target_amount=3000, is_active=True
            )

    def test_fundraising_goal_inactive(self):
        """Test that goals can be marked as inactive."""
        # Clean up first
        FundraisingGoal.objects.filter(goal_type="sponsorship").delete()

        goal = FundraisingGoal.objects.create(
            goal_type="sponsorship", target_amount=15000, is_active=False
        )
        assert goal.is_active is False
