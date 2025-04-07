from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from portal_account.models import PortalProfile

class SignupTests(TestCase):
    def test_signup_requires_tos_agreement(self):
        """Test that signup requires Terms of Service agreement."""
        signup_url = reverse('account_signup')
        
        # Data without tos_agreement
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'testpassword123',
            'coc_agreement': True,
            # tos_agreement is missing
        }
        
        response = self.client.post(signup_url, data)
        
        # Check that the form is invalid
        self.assertEqual(response.status_code, 200)  # Form redisplayed with errors
        self.assertFalse(User.objects.filter(username='testuser').exists())
    
    def test_signup_requires_coc_agreement(self):
        """Test that signup requires Code of Conduct agreement."""
        signup_url = reverse('account_signup')
        
        # Data without coc_agreement
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'testpassword123',
            'tos_agreement': True,
            # coc_agreement is missing
        }
        
        response = self.client.post(signup_url, data)
        
        # Check that the form is invalid
        self.assertEqual(response.status_code, 200)  # Form redisplayed with errors
        self.assertFalse(User.objects.filter(username='testuser').exists())
    
    def test_successful_signup_with_agreements(self):
        """Test that signup succeeds when both agreements are checked."""
        signup_url = reverse('account_signup')
        
        # Complete data with both agreements
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'testpassword123',
            "first_name": "Test",
            "last_name": "User",
            'tos_agreement': True,
            'coc_agreement': True,
        }
        
        response = self.client.post(signup_url, data)
        
        # Check that the user was created and profile has agreement values
        self.assertEqual(response.status_code, 302)  # Redirect after successful signup
        self.assertTrue(User.objects.filter(username='testuser').exists())
        
        # Check that the agreement fields were saved to the profile
        user = User.objects.get(username='testuser')
        profile = PortalProfile.objects.get(user=user)
        self.assertTrue(profile.tos_agreement)
        self.assertTrue(profile.coc_agreement)
