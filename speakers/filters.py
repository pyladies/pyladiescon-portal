import django_filters

from .constants import SessionKind, SessionStatus
from .models import Session


class SessionFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=SessionStatus.choices, empty_label="Any status"
    )
    kind = django_filters.ChoiceFilter(
        choices=SessionKind.choices, empty_label="Any kind"
    )
    search = django_filters.CharFilter(
        field_name="title", lookup_expr="icontains", label="Title contains"
    )

    class Meta:
        model = Session
        fields = ["status", "kind", "search"]
