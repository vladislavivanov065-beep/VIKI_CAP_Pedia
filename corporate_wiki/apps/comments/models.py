"""Comments on an article, with a single level of replies -- see
apps.comments.services.create_comment for how replying to a reply is
handled (attached to the original top-level comment instead of nesting
further), which is what actually enforces the one-level-deep rule; the
self-FK here doesn't stop deeper nesting on its own.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(
        "articles.Article", on_delete=models.CASCADE, related_name="comments"
    )
    # Null for a top-level comment; set for a reply, always to a top-level
    # comment (see apps.comments.services.create_comment) -- never to
    # another reply, so a reply's parent never itself has a parent.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="replies"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comments"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "комментарий"
        verbose_name_plural = "комментарии"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.author}: {self.text[:50]}"
