from __future__ import annotations

from urllib.parse import quote

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.attachments import services
from apps.attachments.exceptions import InvalidAttachmentError
from apps.attachments.models import ArticleAttachment


@require_POST
def attachment_upload(request):
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"error": "Файл не передан."}, status=400)

    try:
        attachment = services.upload_attachment(
            file_obj=uploaded,
            original_filename=uploaded.name or "",
            uploaded_by=request.user,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except InvalidAttachmentError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "id": str(attachment.pk),
            "filename": attachment.original_filename,
            "url": f"/attachments/{attachment.pk}/download/",
            "markdown": f"[[attachment:{attachment.pk}]]",
        }
    )


@require_GET
def attachment_download(request, attachment_id):
    attachment = get_object_or_404(ArticleAttachment, pk=attachment_id)
    data = bytes(attachment.data)
    response = HttpResponse(data, content_type=attachment.mime_type)
    response["Content-Length"] = str(len(data))

    filename = attachment.original_filename or str(attachment.pk)
    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii") or "attachment"
    response["Content-Disposition"] = (
        f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
    )
    return response
