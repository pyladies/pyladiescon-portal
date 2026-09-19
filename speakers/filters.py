import django_filters
from django.contrib.auth.models import User
from django.db.models import Q

from .constants import SessionStatus
from .forms import liaison_candidates
from .models import Presenter, Session, SessionType


class SessionFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=SessionStatus.choices, empty_label="Any status"
    )
    kind = django_filters.ModelChoiceFilter(
        queryset=SessionType.objects.none(), empty_label="Any type", label="Type"
    )
    search = django_filters.CharFilter(
        field_name="title", lookup_expr="icontains", label="Title contains"
    )

    class Meta:
        model = Session
        fields = ["status", "kind", "search"]

    def __init__(self, *args, conference=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["kind"].queryset = SessionType.objects.filter(
            conference=conference
        )


class PresenterFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search", label="Name or email")
    liaison = django_filters.ModelChoiceFilter(
        queryset=User.objects.none(), empty_label="Any liaison"
    )

    class Meta:
        model = Presenter
        fields = ["search", "liaison"]

    def __init__(self, *args, conference=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["liaison"].queryset = liaison_candidates(conference)
        self.filters["liaison"].field.label_from_instance = (
            lambda user: user.get_full_name() or user.username
        )

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(display_name__icontains=value) | Q(email__icontains=value)
        )
