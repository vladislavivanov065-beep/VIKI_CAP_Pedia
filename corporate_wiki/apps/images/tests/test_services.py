from io import BytesIO

import pytest
from django.test import override_settings

from apps.accounts.factories import UserFactory
from apps.images import services
from apps.images.exceptions import (
    ImageDimensionsTooLargeError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from apps.images.models import ArticleImage
from apps.images.tests.factories import make_image_bytes

pytestmark = pytest.mark.django_db


def _upload(data: bytes, *, filename="photo.png", **kwargs):
    uploaded_by = kwargs.pop("uploaded_by", None)
    if uploaded_by is None:
        uploaded_by = UserFactory()
    return services.upload_article_image(
        file_obj=BytesIO(data),
        original_filename=filename,
        uploaded_by=uploaded_by,
        **kwargs,
    )


@pytest.mark.parametrize(
    "image_format,filename", [("JPEG", "a.jpg"), ("PNG", "a.png"), ("GIF", "a.gif")]
)
def test_upload_accepts_jpeg_png_gif(image_format, filename):
    data = make_image_bytes(image_format=image_format)
    image = _upload(data, filename=filename)
    assert image.mime_type == services.FORMAT_MIME_TYPES[image_format]
    assert image.width == 100
    assert image.height == 80


def test_upload_accepts_webp():
    data = make_image_bytes(image_format="WEBP")
    image = _upload(data, filename="a.webp")
    assert image.mime_type == "image/webp"


def test_upload_stores_data_and_thumbnail_in_database_only():
    data = make_image_bytes()
    image = _upload(data)
    assert bytes(image.data)
    assert bytes(image.thumbnail_data)
    # No path/filesystem field exists at all on the model.
    assert not hasattr(image, "path")
    assert not hasattr(image, "file")


def test_thumbnail_is_smaller_than_original():
    data = make_image_bytes(size=(1000, 800))
    image = _upload(data)
    assert image.width == 1000
    from PIL import Image as PILImage

    thumb = PILImage.open(BytesIO(bytes(image.thumbnail_data)))
    assert thumb.width <= 320
    assert thumb.height <= 320


def test_upload_rejects_svg_disguised_as_png_extension():
    svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    with pytest.raises(InvalidImageError):
        _upload(svg_bytes, filename="fake.png")


def test_upload_rejects_corrupted_image_data():
    with pytest.raises(InvalidImageError):
        _upload(b"not an image at all", filename="broken.png")


def test_upload_rejects_file_over_size_limit():
    data = make_image_bytes(size=(50, 50))
    with override_settings(MAX_IMAGE_SIZE_MB=0):  # 0 MB -> anything is "too big"
        with pytest.raises(ImageTooLargeError):
            _upload(data)


def test_upload_rejects_dimensions_over_limit():
    data = make_image_bytes(size=(200, 200))
    with override_settings(MAX_IMAGE_WIDTH=100, MAX_IMAGE_HEIGHT=100):
        with pytest.raises(ImageDimensionsTooLargeError):
            _upload(data)


def test_mime_type_is_checked_by_content_not_extension():
    """A PNG's real bytes saved with a .jpg extension must still be
    detected (and stored) as PNG — the extension is metadata only.
    """
    data = make_image_bytes(image_format="PNG")
    image = _upload(data, filename="totally-a.jpg")
    assert image.mime_type == "image/png"
    assert image.original_filename == "totally-a.jpg"


def test_exif_orientation_is_applied_and_exif_is_stripped():
    from PIL import Image as PILImage

    buffer = BytesIO()
    base = PILImage.new("RGB", (100, 50), (0, 255, 0))
    exif = base.getexif()
    exif[0x0112] = 6  # Orientation: rotate 270
    base.save(buffer, format="JPEG", exif=exif)

    image = _upload(buffer.getvalue(), filename="rotated.jpg")

    stored = PILImage.open(BytesIO(bytes(image.data)))
    # Orientation 6 on a 100x50 image should result in a 50x100 image
    # once baked into the pixels, and no EXIF block should remain.
    assert stored.size == (50, 100)
    assert not stored.getexif()


def test_identical_uploads_are_deduplicated_by_checksum():
    data = make_image_bytes()
    first = _upload(data, filename="one.png")
    second = _upload(data, filename="two.png")
    assert first.pk == second.pk
    assert ArticleImage.objects.count() == 1


def test_unsupported_format_is_rejected():
    from PIL import Image as PILImage

    buffer = BytesIO()
    PILImage.new("RGB", (10, 10)).save(buffer, format="BMP")
    with pytest.raises(UnsupportedImageFormatError):
        _upload(buffer.getvalue(), filename="a.bmp")
