from django.contrib import admin

from .models import Conference


class ActiveConferenceFilter(admin.SimpleListFilter):
    """Conference list filter that defaults to the active edition.

    With no query parameter the changelist shows only the active conference's
    rows, so the admin lands on the current year by default; ``?conference=all``
    shows every edition, and each year remains individually selectable.

    Admins whose model reaches the conference indirectly set ``field_path``
    (e.g. ``"order__conference"``).
    """

    title = "conference"
    parameter_name = "conference"
    field_path = "conference"

    def lookups(self, request, model_admin):
        return [(str(conf.pk), str(conf)) for conf in Conference.objects.all()]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "all":
            return queryset
        if value:
            return queryset.filter(**{f"{self.field_path}__pk": value})
        active = Conference.get_active()
        if active is not None:
            return queryset.filter(**{self.field_path: active})
        return queryset

    def choices(self, changelist):
        active = Conference.get_active()
        value = self.value()
        yield {
            "selected": value == "all",
            "query_string": changelist.get_query_string({self.parameter_name: "all"}),
            "display": "All",
        }
        for pk, title in self.lookup_choices:
            yield {
                "selected": value == pk
                or (value is None and active is not None and str(active.pk) == pk),
                "query_string": changelist.get_query_string({self.parameter_name: pk}),
                "display": title,
            }
