from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ArticleImage(models.Model):
    """A user-uploaded image, stored entirely inside SQLite (section 6).

    Deliberately has no foreign key to any Article/ArticleRevision — an
    image is not owned by a single revision and can be reused across many.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    data = models.BinaryField()
    thumbnail_data = models.BinaryField(null=True, blank=True)

    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()

    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.CharField(max_length=500, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_images",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    checksum = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        verbose_name = "изображение"
        verbose_name_plural = "изображения"
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_filename or str(self.id)
