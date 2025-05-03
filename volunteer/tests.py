from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from volunteer.models import VolunteerProfile

# Create your tests here.

class VolunteerProfileSocialMediaValidationTests(TestCase):
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        self.profile = VolunteerProfile(
            user=self.user,
            timezone="UTC",
            languages_spoken=["en"]
        )
    
    def test_valid_github_username(self):
        valid_usernames = ['user123', 'user-name', 'User123', 'user-123']
        
        for username in valid_usernames:
            self.profile.github_username = username
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid GitHub username '{username}' raised ValidationError: {e}")
    
    def test_invalid_github_username(self):
        invalid_usernames = [
            '-user123',
            'user123-',  
            'user_123',  
            'user 123',  
            'a' * 40     
        ]
        
        for username in invalid_usernames:
            self.profile.github_username = username
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('github_username', context.exception.message_dict)
    
    def test_valid_discord_username(self):
        valid_usernames = ['user123', 'user.name', 'user_name', 'user-name', 'ab']
        
        for username in valid_usernames:
            self.profile.discord_username = username
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid Discord username '{username}' raised ValidationError: {e}")
    
    def test_invalid_discord_username(self):
        invalid_usernames = [
            'a',           
            'a' * 33,      
            'user..name',  
            'user__name',  
            'user--name',  
            'user name',   
            '.username',   
            'username.',   
        ]
        
        for username in invalid_usernames:
            self.profile.discord_username = username
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('discord_username', context.exception.message_dict)
    
    def test_valid_instagram_username(self):
        valid_usernames = ['user123', 'user.name', 'user_name', 'a']
        
        for username in valid_usernames:
            self.profile.instagram_username = username
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid Instagram username '{username}' raised ValidationError: {e}")
    
    def test_invalid_instagram_username(self):
        invalid_usernames = [
            'a' * 31,      
            'user-name',   
            'user name',   
            'user@name',   
        ]
        
        for username in invalid_usernames:
            self.profile.instagram_username = username
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('instagram_username', context.exception.message_dict)
    
    def test_valid_bluesky_username(self):
        valid_usernames = [
            'username',
            'user.name',
            'username.bsky.social',
            'username.domain.com'
        ]
        
        for username in valid_usernames:
            self.profile.bluesky_username = username
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid Bluesky username '{username}' raised ValidationError: {e}")
    
    def test_invalid_bluesky_username(self):
        invalid_usernames = [
            '.username',              
            'username.',              
            'username@bsky.social',   
            'user name.bsky.social',  
        ]
        
        for username in invalid_usernames:
            self.profile.bluesky_username = username
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('bluesky_username', context.exception.message_dict)
    
    def test_valid_mastodon_url(self):
        valid_urls = [
            '@username@mastodon.social',
            '@user_name@instance.org',
            'https://mastodon.social/@username',
            'http://instance.org/@user_name'
        ]
        
        for url in valid_urls:
            self.profile.mastodon_url = url
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid Mastodon URL '{url}' raised ValidationError: {e}")
    
    def test_invalid_mastodon_url(self):
        invalid_urls = [
            'username@mastodon.social',       
            '@username@',                     
            '@username@invalid',              
            'https://mastodon.social/username',  
            'mastodon.social/@username',      
        ]
        
        for url in invalid_urls:
            self.profile.mastodon_url = url
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('mastodon_url', context.exception.message_dict)
    
    def test_valid_x_username(self):
        valid_usernames = ['user123', 'user_name', 'a', 'a' * 15]
        
        for username in valid_usernames:
            self.profile.x_username = username
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid X username '{username}' raised ValidationError: {e}")
    
    def test_invalid_x_username(self):
        invalid_usernames = [
            'a' * 16,    
            'user-name', 
            'user.name', 
            'user name', 
            'user@name', 
        ]
        
        for username in invalid_usernames:
            self.profile.x_username = username
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('x_username', context.exception.message_dict)
    
    def test_valid_linkedin_url(self):
        valid_urls = [
            'linkedin.com/in/username',
            'www.linkedin.com/in/username',
            'http://www.linkedin.com/in/username',
            'https://www.linkedin.com/in/username',
            'https://www.linkedin.com/in/user-name',
            'https://www.linkedin.com/in/user_name',
            'https://www.linkedin.com/in/username/'
        ]
        
        for url in valid_urls:
            self.profile.linkedin_url = url
            try:
                self.profile.full_clean()
            except ValidationError as e:
                self.fail(f"Valid LinkedIn URL '{url}' raised ValidationError: {e}")
    
    def test_invalid_linkedin_url(self):
        invalid_urls = [
            'username',                       
            'linkedin.com/username',          
            'https://www.linkedin.com/username',
            'https://linkedin.com/in/user name',
            'https://other-site.com/in/username',
        ]
        
        for url in invalid_urls:
            self.profile.linkedin_url = url
            with self.assertRaises(ValidationError) as context:
                self.profile.full_clean()
            self.assertIn('linkedin_url', context.exception.message_dict)