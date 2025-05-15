import pytest
from django.urls import reverse
from pytest_django.asserts import assertTemplateUsed


@pytest.mark.django_db
class TestIndexView:
    def test_access(self, client):
        """
        Test users can access the index page.
        Should return 200 status code and render the correct template.
        """
        response = client.get(reverse("index"))
        
        assert response.status_code == 200
        assertTemplateUsed(response, "portal/index.html")