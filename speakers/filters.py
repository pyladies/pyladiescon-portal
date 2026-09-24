import django_filters
from django.contrib.auth.models import User
from django.db.models import Q

from .constants import UNACCEPTED_STATUSES, SessionStatus
from .models import Presenter, Session, SessionType
from .people import liaison_candidates


class SessionFilter(django_filters.FilterSet):
    """The organizers' sessions list.

    Proposed and rejected sessions are hidden unless the reader asks for
    them by status: the list is the program, and a proposal is a request
    that has its own queue.
    """

    status = django_filters.ChoiceFilter(
        choices=SessionStatus.choices, empty_label="Any status (on the program)"
    )
    source = django_filters.ChoiceFilter(
        method="filter_source",
        empty_label="Anyone",
        label="Added by",
        choices=[
            ("organizers", "Organizers"),
            ("speakers", "A speaker or a proposal"),
        ],
    )
    kind = django_filters.ModelChoiceFilter(
        queryset=SessionType.objects.none(), empty_label="Any type", label="Type"
    )
    search = django_filters.CharFilter(
        field_name="title", lookup_expr="icontains", label="Title contains"
    )

    class Meta:
        model = Session
        fields = ["status", "kind", "search", "source"]

    def __init__(self, *args, conference=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["kind"].queryset = SessionType.objects.filter(
            conference=conference
        )

    def filter_source(self, queryset, name, value):
        return queryset.filter(created_by_presenter=value == "speakers")

    @property
    def qs(self):
        """Hide proposals unless the reader asked for a status.

        Read from the raw query string rather than the cleaned data: this
        runs for an unbound form too, and an unbound form has none.
        """
        queryset = super().qs
        if (self.data or {}).get("status"):
            return queryset
        return queryset.exclude(status__in=UNACCEPTED_STATUSES)


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
