import pytest
from allauth.account.forms import SignupForm
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse

from portal.forms import CustomSignupForm

User = get_user_model()


@pytest.mark.django_db
class TestCustomSignupForm:
    @pytest.fixture
    def form_data(self):
        return {
            "username": "testuser",
            "email": "test@example.com",
            "password1": "securepassword123",
            "password2": "securepassword123",
            "first_name": "Test",
            "last_name": "User",
            "coc_agreement": True,
            "tos_agreement": True,
        }

    @pytest.fixture
    def request_with_session(self, client):
        """Create a request with session using the Django test client"""
        # Make a dummy GET request
        response = client.get(reverse("account_signup"))
        request = response.wsgi_request

        # Attach session middleware if not already
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()

        return request

    def test_form_inherits_from_allauth(self):
        """Ensure CustomSignupForm inherits from allauth's SignupForm"""
        assert issubclass(CustomSignupForm, SignupForm)

    def test_form_has_custom_fields(self):
        """Custom fields should be included and labeled correctly"""
        form = CustomSignupForm()
        assert "first_name" in form.fields
        assert "last_name" in form.fields
        assert form.fields["first_name"].label == "First Name"
        assert form.fields["last_name"].label == "Last Name"

    def test_form_save_method(self, form_data, request_with_session):
        """Check that the form saves user with correct fields"""
        form = CustomSignupForm(data=form_data)
        assert form.is_valid()

        user = form.save(request_with_session)
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    def test_form_validation_missing_names(self):
        """Validation should fail if first/last name are missing"""
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password1": "securepassword123",
            "password2": "securepassword123",
        }
        form = CustomSignupForm(data=data)
        assert not form.is_valid()
        assert "first_name" in form.errors
        assert "last_name" in form.errors

    def test_form_widget_attrs(self):
        """Ensure widget attributes are set correctly"""
        form = CustomSignupForm()
        assert form.fields["first_name"].widget.attrs["placeholder"] == "First Name"
        assert form.fields["last_name"].widget.attrs["placeholder"] == "Last Name"
