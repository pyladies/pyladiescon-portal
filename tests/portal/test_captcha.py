import pytest
from captcha.conf import settings as captcha_settings
from captcha.models import CaptchaStore
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains


@pytest.mark.django_db
class TestSignupCaptcha:

    signup_data = {
        "username": "newuser",
        "email": "newuser@example.com",
        "first_name": "New",
        "last_name": "User",
        "password1": "a-long-enough-password",
        "password2": "a-long-enough-password",
        "coc_agreement": "on",
        "tos_agreement": "on",
    }

    def test_signup_page_renders_captcha_image(self, client):
        response = client.get(reverse("account_signup"))
        assertContains(response, 'name="captcha_0"')
        assertContains(response, 'name="captcha_1"')
        assertContains(response, "/captcha/image/")

    def test_audio_alternative_is_an_inline_player(self, client, monkeypatch):
        # The package copies Django settings into captcha.conf.settings at
        # import, so patch that. Rendering only checks the path is set; only
        # the audio view itself runs flite.
        monkeypatch.setattr(captcha_settings, "CAPTCHA_FLITE_PATH", "/usr/bin/flite")
        response = client.get(reverse("account_signup"))
        assertContains(response, "Or listen to the characters")
        assertContains(response, 'width="320"')
        assertContains(response, 'height="90"')
        assertContains(response, '<audio controls preload="none" src="/captcha/audio/')

    def test_no_audio_link_without_flite(self, client, monkeypatch):
        monkeypatch.setattr(captcha_settings, "CAPTCHA_FLITE_PATH", None)
        response = client.get(reverse("account_signup"))
        assert "/captcha/audio/" not in response.content.decode()
        assertContains(response, "/captcha/image/")

    def test_captcha_image_is_served_locally(self, client):
        key = CaptchaStore.generate_key()
        response = client.get(reverse("captcha-image", kwargs={"key": key}))
        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"

    def test_signup_without_captcha_creates_no_user(self, client, django_user_model):
        response = client.post(reverse("account_signup"), self.signup_data)
        assertContains(response, "This field is required")
        assert not django_user_model.objects.filter(username="newuser").exists()

    def test_signup_with_wrong_answer_creates_no_user(
        self, client, django_user_model, captcha_solution
    ):
        data = {**self.signup_data, **captcha_solution, "captcha_1": "wrong"}
        response = client.post(reverse("account_signup"), data)
        assertContains(response, "Invalid CAPTCHA")
        assert not django_user_model.objects.filter(username="newuser").exists()

    def test_signup_with_right_answer_creates_user(
        self, client, django_user_model, captcha_solution
    ):
        data = {**self.signup_data, **captcha_solution}
        response = client.post(reverse("account_signup"), data)
        assert response.status_code == 302
        assert django_user_model.objects.filter(username="newuser").exists()

    def test_solved_challenge_cannot_be_replayed(
        self, client, django_user_model, captcha_solution
    ):
        client.post(reverse("account_signup"), {**self.signup_data, **captcha_solution})
        replay = {**self.signup_data, **captcha_solution, "username": "second"}
        # A fresh client: the first one is parked on allauth's verify-email step.
        response = Client().post(reverse("account_signup"), replay)
        assertContains(response, "Invalid CAPTCHA")
        assert not django_user_model.objects.filter(username="second").exists()
