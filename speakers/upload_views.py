"""The multipart upload endpoints (design §8.8, task 5.1): JSON in, JSON out.

The browser starts an upload, asks for presigned part URLs in batches,
PUTs the parts to the bucket itself, and asks the portal to complete or
abort. Every endpoint is scoped to a session of the active edition, and
who may upload what is ``media.can_upload``: organizers any kind, a
presenter on the session their raw video.
"""

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from .constants import UPLOAD_PART_URL_BATCH
from .media import (
    MediaStorageNotConfigured,
    UploadError,
    abort_upload,
    can_download,
    can_upload,
    complete_upload,
    part_urls,
    received_parts,
    start_upload,
)
from .mixins import SpeakerModuleRequiredMixin
from .models import MediaAsset, MediaUpload, Session
from .permissions import is_speaker_organizer


def _payload(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        raise UploadError("The request body is not JSON.")


def _upload_json(upload, **extra):
    data = {
        "upload": upload.pk,
        "status": upload.status,
        "kind": upload.kind,
        "language": upload.language,
        "filename": upload.filename,
        "size_bytes": upload.size_bytes,
        "part_size": upload.part_size,
        "parts_total": upload.parts_total,
        "expires_at": upload.expires_at.isoformat(),
    }
    data.update(extra)
    return data


class UploadEndpoint(LoginRequiredMixin, SpeakerModuleRequiredMixin, View):
    """Shared plumbing: the session, the upload, the error shapes."""

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except UploadError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except MediaStorageNotConfigured:
            return JsonResponse(
                {"error": "Object storage is not configured on this portal."},
                status=503,
            )

    def get_session(self):
        return get_object_or_404(
            Session, conference=self.conference, slug=self.kwargs["slug"]
        )

    def get_upload(self, session):
        """An upload of this session the caller may act on: their own, or
        any when they organize."""
        upload = get_object_or_404(MediaUpload, pk=self.kwargs["pk"], session=session)
        if upload.started_by_id != self.request.user.pk and not is_speaker_organizer(
            self.request.user
        ):
            raise PermissionDenied("This is not your upload.")
        return upload


class UploadStartView(UploadEndpoint):
    """POST {kind, language?, filename, size_bytes, content_type?}: open an
    upload and return its first batch of part URLs."""

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, slug):
        session = self.get_session()
        data = _payload(request)
        kind = str(data.get("kind", ""))
        if not can_upload(request.user, session, kind):
            raise PermissionDenied("You may not upload this kind of file here.")
        try:
            size_bytes = int(data.get("size_bytes", 0))
        except (TypeError, ValueError):
            raise UploadError("size_bytes must be a number.")
        upload = start_upload(
            session=session,
            kind=kind,
            language=str(data.get("language", "") or "")[:10],
            filename=str(data.get("filename", "") or ""),
            size_bytes=size_bytes,
            content_type=str(data.get("content_type", "") or "")[:100],
            user=request.user,
        )
        return JsonResponse(_upload_json(upload, parts=part_urls(upload)), status=201)


class UploadDetailView(UploadEndpoint):
    """GET: where the upload stands, with the parts the bucket already holds,
    for a browser that comes back after a dropped connection."""

    def get(self, request, slug, pk):
        upload = self.get_upload(self.get_session())
        return JsonResponse(_upload_json(upload, received=received_parts(upload)))


class UploadPartsView(UploadEndpoint):
    """GET ?from=&count=: the next batch of presigned part URLs."""

    def get(self, request, slug, pk):
        upload = self.get_upload(self.get_session())
        try:
            start = int(request.GET.get("from", 1))
            count = int(request.GET.get("count", UPLOAD_PART_URL_BATCH))
        except ValueError:
            raise UploadError("from and count must be numbers.")
        if start < 1 or start > upload.parts_total:
            raise Http404("No such part.")
        return JsonResponse({"parts": part_urls(upload, start, count)})


class UploadCompleteView(UploadEndpoint):
    """POST {parts: [{number, etag}]}: finalize and record the asset."""

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, slug, pk):
        upload = self.get_upload(self.get_session())
        parts = _payload(request).get("parts")
        if not isinstance(parts, list) or not all(isinstance(p, dict) for p in parts):
            raise UploadError("parts must be a list of {number, etag}.")
        asset = complete_upload(upload, parts)
        return JsonResponse(
            _upload_json(
                upload,
                asset={
                    "id": asset.pk,
                    "version": asset.version,
                    "status": asset.status,
                    "size_bytes": asset.size_bytes,
                },
            )
        )


class UploadAbortView(UploadEndpoint):
    """POST: give the upload up; the bucket drops the parts."""

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, slug, pk):
        upload = self.get_upload(self.get_session())
        return JsonResponse(_upload_json(abort_upload(upload)))


class MediaDownloadView(LoginRequiredMixin, SpeakerModuleRequiredMixin, View):
    """GET: send the caller to a fresh presigned link for the asset.

    Links are minted on the click rather than rendered into the page, so
    a page left open does not hand out stale ones, and the file list
    costs no signing at all to render.
    """

    def get(self, request, slug, pk):
        session = get_object_or_404(
            Session, conference=self.conference, slug=self.kwargs["slug"]
        )
        if not can_download(request.user, session):
            raise PermissionDenied("You may not fetch this session's files.")
        asset = get_object_or_404(MediaAsset, pk=pk, session=session)
        try:
            url = asset.download_url()
        except MediaStorageNotConfigured:
            raise Http404("Object storage is not configured on this portal.")
        if not url:
            raise Http404("This asset has no file.")
        return HttpResponseRedirect(url)


class MediaNotesView(LoginRequiredMixin, SpeakerModuleRequiredMixin, View):
    """POST notes_md: the reviewer's note on an asset ("audio clips at
    4:10"); organizers only."""

    @method_decorator(require_POST)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, slug, pk):
        session = get_object_or_404(
            Session, conference=self.conference, slug=self.kwargs["slug"]
        )
        if not is_speaker_organizer(request.user):
            raise PermissionDenied("Only organizers annotate files.")
        asset = get_object_or_404(MediaAsset, pk=pk, session=session)
        asset.notes_md = request.POST.get("notes_md", "").strip()
        asset.save(update_fields=["notes_md", "modified_date"])
        messages.success(request, "Note saved.")
        return redirect(f"{session.get_absolute_url()}#files")
