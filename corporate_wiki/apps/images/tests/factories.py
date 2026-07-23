from io import BytesIO

from PIL import Image


def make_image_bytes(
    *, image_format: str = "PNG", size: tuple[int, int] = (100, 80), color=(255, 0, 0)
) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB" if image_format != "PNG" else "RGBA", size, color)
    image.save(buffer, format=image_format)
    return buffer.getvalue()
