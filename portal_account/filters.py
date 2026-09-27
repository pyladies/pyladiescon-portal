"""Filters for the Maintenance > Emails trail."""

import django_filters
from django import forms
from django.db.models import Q

from common.models import SentEmail, SentEmailStatus, kind_of
from portal.models import Conference
from speakers.models import Presenter


class PresenterChoiceField(forms.ModelChoiceField):
    """A presenter with their edition: the list spans every year."""

    def label_from_instance(self, presenter):
        return f"{presenter.display_name} ({presenter.conference.year})"


class PresenterFilter(django_filters.ModelChoiceFilter):
    field_class = PresenterChoiceField


class SentEmailFilter(django_filters.FilterSet):
    """Edition, presenter, kind, outcome, and a search on subject or address."""

    conference = django_filters.ModelChoiceFilter(
        queryset=Conference.objects.order_by("-year"),
        empty_label="Any edition",
        label="Edition",
    )
    presenter = PresenterFilter(
        queryset=Presenter.objects.select_related("conference").order_by(
            "display_name", "-conference__year"
        ),
        method="filter_presenter",
        empty_label="Anyone",
        label="Presenter",
    )
    template = django_filters.ChoiceFilter(
        choices=[], empty_label="Any kind", label="Kind"
    )
    status = django_filters.ChoiceFilter(
        choices=SentEmailStatus.choices, empty_label="Sent or failed", label="Outcome"
    )
    search = django_filters.CharFilter(
        method="filter_search", label="Subject or address contains"
    )

    class Meta:
        model = SentEmail
        fields = ["conference", "presenter", "template", "status", "search"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The kinds are whatever has actually been sent, named without the
        # ``emails/`` prefix and the ``.md`` suffix.
        templates = (
            SentEmail.objects.order_by("template")
            .values_list("template", flat=True)
            .distinct()
        )
        self.filters["template"].extra["choices"] = [
            (template, kind_of(template)) for template in templates
        ]

    def filter_presenter(self, queryset, name, value):
        """Sent to them, or about them: the organizers' copy of a proposal
        names the proposer in its digest without being theirs."""
        return queryset.filter(
            Q(presenter=value) | Q(context_digest__presenter=value.pk)
        )

    def filter_search(self, queryset, name, value):
        return queryset.filter(Q(subject__icontains=value) | Q(to__icontains=value))
