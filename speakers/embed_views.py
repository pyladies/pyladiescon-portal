"""The iframe embed (task 6.4, design §11.2): the widget on a bare portal
page, for websites that can't add a script tag.

Framing is allowed on purpose: the page shows only the public program and
has nothing to click that changes anything, so there is no clickjacking
to guard against. Inside a frame it tells the host page its height
(``static/js/embed-frame.js``), so a host that listens can fit the frame.
"""

import re

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import TemplateView

from .api_views import ApiConferenceMixin

VIEWS = {"schedule": "schedule", "sessions": "sessions", "speakers": "speakers"}
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")


@method_decorator(xframe_options_exempt, name="dispatch")
class EmbedView(ApiConferenceMixin, TemplateView):
    template_name = "speakers/embed.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        view = self.kwargs["view"]
        if view not in VIEWS:
            raise Http404("No such view.")
        accent = self.request.GET.get("accent", "")
        context.update(
            conference=self.conference,
            view=view,
            accent=accent if HEX_COLOUR.fullmatch(accent) else "",
        )
        return context

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        response["Cache-Control"] = (
            "no-store" if "preview" in self.request.GET else "public, max-age=300"
        )
        return response
