"""Bulk download pages (design §8.8, "Bulk download", task 5.6).

The export page takes a scope and shows what it would fetch; making the
export records it and leads to its page, which offers the three ways to
get the files: the browser's folder download, the script (with the aria2
file and the manifest), and the zip when the selection is small enough.
Organizers only; the Maintenance list shows who exported what.
"""

import io

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from common.mixins import MaintainerRequiredMixin

from .constants import MediaKind, ZipStatus
from .exports import (
    ExportError,
    clean_scope,
    create_export,
    export_entries,
    exports_for_maintenance,
    manifest_path,
    scope_summary,
    select_assets,
    sessions_with_files,
    write_aria2,
    write_manifest,
    write_script,
    zip_url,
)
from .media import MediaBucket, MediaStorageNotConfigured
from .mixins import SpeakerOrganizerRequiredMixin
from .models import MediaExport

FILES = {
    "download.sh": ("application/x-sh", "download.sh"),
    "aria2.txt": ("text/plain", "aria2.txt"),
    "manifest.csv": ("text/csv", "manifest.csv"),
    "entries.json": ("application/json", None),
}


def scope_from_query(query):
    """The scope a page's query string or form describes."""
    return clean_scope(
        {
            "kinds": query.getlist("kinds"),
            "language": query.get("language", ""),
            "sessions": query.getlist("sessions"),
            "versions": query.get("versions", "latest"),
            "since": query.get("since", ""),
        }
    )


class MediaExportView(LoginRequiredMixin, SpeakerOrganizerRequiredMixin, View):
    """GET: the scope form with a live preview of the count and bytes;
    POST: record the export and go to its page."""

    template_name = "speakers/media_export.html"

    def get(self, request):
        try:
            scope = scope_from_query(request.GET)
        except (ExportError, ValueError):
            messages.error(request, "That selection could not be read; start again.")
            return redirect("speakers:media_export")
        assets = select_assets(self.conference, request.user, scope)
        return render(
            request,
            self.template_name,
            {
                "conference": self.conference,
                "rail_active": "sessions",
                "scope": scope,
                "kinds": MediaKind.choices,
                "sessions": sessions_with_files(self.conference, request.user),
                "file_count": len(assets),
                "total_bytes": sum(a.size_bytes or 0 for a in assets),
                "zip_max_bytes": settings.SPEAKER_MEDIA_ZIP_MAX_BYTES,
                "recent": MediaExport.objects.filter(
                    conference=self.conference, created_by=request.user
                ).order_by("-id")[:5],
            },
        )

    def post(self, request):
        try:
            scope = scope_from_query(request.POST)
        except (ExportError, ValueError):
            messages.error(request, "That selection could not be read; start again.")
            return redirect("speakers:media_export")
        export = create_export(self.conference, request.user, scope)
        if not export.file_count:
            messages.warning(request, "Nothing matches that selection.")
        return redirect(export.get_absolute_url())


class ExportScopedMixin(LoginRequiredMixin, SpeakerOrganizerRequiredMixin):
    def get_export(self):
        return get_object_or_404(
            MediaExport.objects.select_related("conference", "created_by"),
            pk=self.kwargs["pk"],
            conference=self.conference,
        )


class MediaExportDetailView(ExportScopedMixin, View):
    """The export's page: what it holds and the three ways to fetch it."""

    def get(self, request, pk):
        export = self.get_export()
        context = {
            "conference": self.conference,
            "rail_active": "sessions",
            "export": export,
            "summary": scope_summary(export.scope),
            "zip_allowed": export.total_bytes <= settings.SPEAKER_MEDIA_ZIP_MAX_BYTES,
            "zip_link": "",
            "storage_ready": True,
        }
        if not export.is_expired:
            try:
                MediaBucket.from_settings()
                context["zip_link"] = zip_url(export)
            except MediaStorageNotConfigured:
                context["storage_ready"] = False
        return render(request, "speakers/media_export_detail.html", context)


class MediaExportFileView(ExportScopedMixin, View):
    """GET download.sh, aria2.txt, manifest.csv or entries.json: built on
    the request with links living until the export expires."""

    def get(self, request, pk, name):
        if name not in FILES:
            raise Http404("No such file.")
        export = self.get_export()
        try:
            entries = export_entries(
                export, request.user, with_urls=name != "manifest.csv"
            )
        except ExportError as exc:
            raise Http404(str(exc))
        except MediaStorageNotConfigured:
            raise Http404("Object storage is not configured on this portal.")
        content_type, filename = FILES[name]
        if name == "entries.json":
            return JsonResponse(
                {
                    "export": export.pk,
                    "expires_at": export.expires_at.isoformat(),
                    "manifest_path": manifest_path(export),
                    "manifest": write_manifest(entries, io.StringIO()).getvalue(),
                    "files": [
                        {"path": e["path"], "url": e["url"], "size": e["size"]}
                        for e in entries
                    ],
                }
            )
        response = HttpResponse(content_type=f"{content_type}; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        if name == "download.sh":
            write_script(export, entries, response)
        elif name == "aria2.txt":
            write_aria2(entries, response)
        else:
            write_manifest(entries, response)
        return response


class MediaExportZipView(ExportScopedMixin, View):
    """POST: ask the media worker for the zip."""

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        from .tasks import build_export_zip_task

        export = self.get_export()
        if export.is_expired:
            messages.error(request, "This export has expired; make a new one.")
            return redirect(export.get_absolute_url())
        if export.total_bytes > settings.SPEAKER_MEDIA_ZIP_MAX_BYTES:
            messages.error(
                request,
                "This selection is too large for a zip; use the folder download "
                "or the script.",
            )
            return redirect(export.get_absolute_url())
        if export.zip_status in (ZipStatus.QUEUED, ZipStatus.RUNNING):
            messages.info(request, "The zip is already being built.")
            return redirect(export.get_absolute_url())
        export.zip_status = ZipStatus.QUEUED
        export.zip_error = ""
        export.save(update_fields=["zip_status", "zip_error", "modified_date"])
        build_export_zip_task.delay(export.pk)
        messages.success(
            request, "Building the zip; you will get an email with the link."
        )
        return redirect(export.get_absolute_url())


class MaintenanceExportsView(MaintainerRequiredMixin, ListView):
    """Maintenance > Exports: who pulled which files, and when."""

    template_name = "speakers/maintenance_exports.html"
    paginate_by = 50

    def get_queryset(self):
        return exports_for_maintenance()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for export in context["object_list"]:
            export.summary = scope_summary(export.scope)
        return context
