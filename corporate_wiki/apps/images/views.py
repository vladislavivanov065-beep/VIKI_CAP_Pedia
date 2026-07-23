from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import condition, require_GET, require_POST

from apps.images import services
from apps.images.exceptions import InvalidImageError
from apps.images.models import ArticleImage


def _checksum_etag(request, image_id, *_args, **_kwargs):
    try:
        return ArticleImage.objects.filter(pk=image_id).values_list("checksum", flat=True).first()
    except (ValueError, ValidationError):
        return None


def _thumbnail_etag(request, image_id, *_args, **_kwargs):
    checksum = _checksum_etag(request, image_id)
    return f"{checksum}-thumb" if checksum else None


@require_GET
@condition(etag_func=_checksum_etag)
def image_original(request, image_id):
    image = get_object_or_404(ArticleImage, pk=image_id)
    response = HttpResponse(bytes(image.data), content_type=image.mime_type)
    response["Content-Length"] = str(len(image.data))
    response["Cache-Control"] = "private, max-age=86400"
    return response


@require_GET
@condition(etag_func=_thumbnail_etag)
def image_thumbnail(request, image_id):
    image = get_object_or_404(ArticleImage, pk=image_id)
    data = bytes(image.thumbnail_data or image.data)
    response = HttpResponse(data, content_type=image.mime_type)
    response["Content-Length"] = str(len(data))
    response["Cache-Control"] = "private, max-age=86400"
    return response


@require_POST
def image_upload(request):
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"error": "Файл не передан."}, status=400)

    try:
        image = services.upload_article_image(
            file_obj=uploaded,
            original_filename=uploaded.name or "",
            uploaded_by=request.user,
            alt_text=request.POST.get("alt_text", ""),
            caption=request.POST.get("caption", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except InvalidImageError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "id": str(image.pk),
            "url": f"/images/{image.pk}/",
            "thumbnail_url": f"/images/{image.pk}/thumbnail/",
            "markdown": f"![[image:{image.pk}]]",
        }
    )
