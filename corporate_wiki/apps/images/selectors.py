from __future__ import annotations

import uuid

from apps.images.models import ArticleImage


def get_image(image_id: uuid.UUID | str) -> ArticleImage:
    return ArticleImage.objects.get(pk=image_id)
