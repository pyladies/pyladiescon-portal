from io import StringIO

import pytest
from django.contrib.sites.models import Site
from django.core.management import call_command


@pytest.mark.django_db
class TestSetSiteDomain:
    def test_sets_domain_and_defaults_name(self):
        out = StringIO()
        call_command("set_site_domain", "localhost:8000", stdout=out)
        site = Site.objects.get_current()
        assert site.domain == "localhost:8000" and site.name == "localhost:8000"
        assert "is now localhost:8000" in out.getvalue()

    def test_explicit_name(self):
        call_command("set_site_domain", "portal.example.org", name="PyLadiesCon Portal")
        site = Site.objects.get_current()
        assert site.domain == "portal.example.org"
        assert site.name == "PyLadiesCon Portal"
