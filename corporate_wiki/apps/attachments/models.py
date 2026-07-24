from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class ArticleAttachment(models.Model):
    """A user-uploaded document, stored entirely inside SQLite — same
    reasoning as ``apps.images.ArticleImage``: no filesystem/media
    directory, referenced by ID from article Markdown so one upload can
    be linked from multiple articles.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    data = models.BinaryField()

    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_attachments",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    checksum = models.CharField(max_length=64, unique=True, editable=False)

    class Meta:
        verbose_name = "вложение"
        verbose_name_plural = "вложения"
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_filename or str(self.id)
