from django.test import TestCase
from django.template import Context, Template
from django.contrib.auth.models import User

from volunteer.models import Language, VolunteerProfile


class VolunteerTemplateTagsTest(TestCase):
    """Test volunteer template tags functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        
        self.volunteer_profile = VolunteerProfile.objects.create(
            user=self.user,
            availability_hours_per_week=10
        )
        
        # Create test languages
        self.english = Language.objects.create(name="English", code="en")
        self.spanish = Language.objects.create(name="Spanish", code="es")
        self.french = Language.objects.create(name="French", code="fr")
        
        # Add languages to volunteer profile
        self.volunteer_profile.language.add(self.english, self.spanish)

    def test_render_volunteer_languages_simple_tag(self):
        """Test the render_volunteer_languages simple tag."""
        template = Template("""
            {% load volunteer_tags %}
            {% render_volunteer_languages volunteer_profile %}
        """)
        
        context = Context({"volunteer_profile": self.volunteer_profile})
        rendered = template.render(context)
        
        self.assertIn("English", rendered)
        self.assertIn("Spanish", rendered)
        self.assertIn("badge bg-info text-dark me-1", rendered)
        self.assertNotIn("French", rendered)

    def test_render_volunteer_languages_with_custom_css(self):
        """Test the render_volunteer_languages simple tag with custom CSS."""
        template = Template("""
            {% load volunteer_tags %}
            {% render_volunteer_languages volunteer_profile "custom-badge" %}
        """)
        
        context = Context({"volunteer_profile": self.volunteer_profile})
        rendered = template.render(context)
        
        self.assertIn("English", rendered)
        self.assertIn("Spanish", rendered)
        self.assertIn("custom-badge", rendered)
        self.assertNotIn("badge bg-info text-dark me-1", rendered)

    def test_volunteer_languages_badges_inclusion_tag(self):
        """Test the volunteer_languages_badges inclusion tag."""
        template = Template("""
            {% load volunteer_tags %}
            {% volunteer_languages_badges volunteer_profile %}
        """)
        
        context = Context({"volunteer_profile": self.volunteer_profile})
        rendered = template.render(context)
        
        self.assertIn("English", rendered)
        self.assertIn("Spanish", rendered)
        self.assertIn("badge bg-info text-dark me-1", rendered)
        self.assertNotIn("French", rendered)

    def test_volunteer_languages_badges_with_custom_css(self):
        """Test the volunteer_languages_badges inclusion tag with custom CSS."""
        template = Template("""
            {% load volunteer_tags %}
            {% volunteer_languages_badges volunteer_profile "custom-style" %}
        """)
        
        context = Context({"volunteer_profile": self.volunteer_profile})
        rendered = template.render(context)
        
        self.assertIn("English", rendered)
        self.assertIn("Spanish", rendered)
        self.assertIn("custom-style", rendered)
        self.assertNotIn("badge bg-info text-dark me-1", rendered)

    def test_template_tags_with_no_languages(self):
        """Test template tags when volunteer has no languages."""
        # Create volunteer with no languages
        user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123"
        )
        volunteer_profile2 = VolunteerProfile.objects.create(
            user=user2,
            availability_hours_per_week=5
        )
        
        template = Template("""
            {% load volunteer_tags %}
            {% render_volunteer_languages volunteer_profile %}
        """)
        
        context = Context({"volunteer_profile": volunteer_profile2})
        rendered = template.render(context)
        
        # Should render empty string when no languages
        self.assertEqual(rendered.strip(), "")

    def test_template_tags_with_none_profile(self):
        """Test template tags when volunteer_profile is None."""
        template = Template("""
            {% load volunteer_tags %}
            {% render_volunteer_languages volunteer_profile %}
        """)
        
        context = Context({"volunteer_profile": None})
        rendered = template.render(context)
        
        # Should render empty string when profile is None
        self.assertEqual(rendered.strip(), "")

    def test_template_tags_with_missing_profile(self):
        """Test template tags when volunteer_profile is not in context."""
        template = Template("""
            {% load volunteer_tags %}
            {% render_volunteer_languages volunteer_profile %}
        """)
        
        context = Context({})
        rendered = template.render(context)
        
        # Should render empty string when profile is missing
        self.assertEqual(rendered.strip(), "")