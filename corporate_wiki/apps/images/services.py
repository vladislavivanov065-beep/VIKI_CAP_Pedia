"""Image upload pipeline (section 6.5).

Every uploaded image is fully decoded, validated, stripped of EXIF,
re-encoded and thumbnailed before anything touches the database — nothing
here ever gets written to disk.

Animated GIFs are intentionally flattened to their first frame: the spec
only requires *supporting* the GIF format, not preserving animation, and
keeping every format on one single-frame pipeline keeps the processing
(and its attack surface) uniform.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import BinaryIO

from django.conf import settings
from PIL import Image, ImageOps

from apps.accounts.models import User
from apps.images.exceptions import (
    ImageDimensionsTooLargeError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from apps.images.models import ArticleImage

FORMAT_MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
THUMBNAIL_SIZE = (320, 320)


def _read_all(file_obj: BinaryIO) -> bytes:
    file_obj.seek(0)
    return file_obj.read()


def _encode_single_frame(image: Image.Image, image_format: str) -> bytes:
    buffer = BytesIO()
    if image_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=90)
    elif image_format == "PNG":
        image.save(buffer, format="PNG", optimize=True)
    elif image_format == "WEBP":
        image.save(buffer, format="WEBP", quality=90)
    else:
        image.save(buffer, format=image_format)
    return buffer.getvalue()


def upload_article_image(
    *,
    file_obj: BinaryIO,
    original_filename: str,
    uploaded_by: User,
    alt_text: str = "",
    caption: str = "",
) -> ArticleImage:
    raw_bytes = _read_all(file_obj)

    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise ImageTooLargeError(f"Изображение больше {settings.MAX_IMAGE_SIZE_MB} МБ.")

    try:
        Image.open(BytesIO(raw_bytes)).verify()
    except Exception as exc:
        raise InvalidImageError("Файл повреждён или не является изображением.") from exc

    try:
        image = Image.open(BytesIO(raw_bytes))
        image.load()
        image_format = image.format
    except Exception as exc:
        raise InvalidImageError("Файл повреждён или не является изображением.") from exc

    if image_format not in FORMAT_MIME_TYPES:
        raise UnsupportedImageFormatError(f"Формат {image_format} не поддерживается.")

    if image.width > settings.MAX_IMAGE_WIDTH or image.height > settings.MAX_IMAGE_HEIGHT:
        raise ImageDimensionsTooLargeError("Слишком большое разрешение изображения.")

    upright_image: Image.Image = ImageOps.exif_transpose(image) or image
    encoded_data = _encode_single_frame(upright_image, image_format)

    # Re-open the freshly encoded bytes so stored width/height always
    # match exactly what gets served.
    final_image = Image.open(BytesIO(encoded_data))
    width, height = final_image.size

    thumbnail_image = final_image.copy()
    thumbnail_image.thumbnail(THUMBNAIL_SIZE)
    thumbnail_data = _encode_single_frame(thumbnail_image, image_format)

    checksum = hashlib.sha256(encoded_data).hexdigest()

    existing = ArticleImage.objects.filter(checksum=checksum).first()
    if existing is not None:
        return existing

    return ArticleImage.objects.create(
        data=encoded_data,
        thumbnail_data=thumbnail_data,
        original_filename=(original_filename or "")[:255],
        mime_type=FORMAT_MIME_TYPES[image_format],
        file_size=len(encoded_data),
        width=width,
        height=height,
        alt_text=alt_text,
        caption=caption,
        uploaded_by=uploaded_by,
        checksum=checksum,
    )
