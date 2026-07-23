from __future__ import annotations

import hashlib
import uuid

from django.conf import settings
from django.db import models


class Article(models.Model):
    """A wiki page. Content itself always lives in ``ArticleRevision`` —
    this row only tracks identity, current pointer and lifecycle state.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    # Lower-cased, whitespace-stripped mirror of `title`, kept in sync in
    # save(). Backs the case-insensitive-among-active-articles uniqueness
    # rule below, since SQLite has no case-insensitive collation for that
    # out of the box.
    title_normalized = models.CharField(max_length=255, editable=False)
    slug = models.SlugField(max_length=255, unique=True, allow_unicode=True)

    current_revision = models.ForeignKey(
        "articles.ArticleRevision",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_articles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_articles",
    )

    # Optimistic-locking counter (section 4.5). Bumped by one on every
    # edit/rename/restore alongside a new ArticleRevision.
    version = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "статья"
        verbose_name_plural = "статьи"
        ordering = ["title"]
        constraints = [
            models.UniqueConstraint(
                fields=["title_normalized"],
                condition=models.Q(is_archived=False),
                name="unique_active_article_title_normalized",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        self.title_normalized = self.title.strip().lower()
        super().save(*args, **kwargs)


class ArticleRevision(models.Model):
    """One immutable snapshot of an article's title and content.

    Never updated or deleted through any code path — editing always means
    creating a new row and repointing ``Article.current_revision`` at it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="revisions")
    revision_number = models.PositiveIntegerField()

    title = models.CharField(max_length=255)
    content_source = models.TextField(blank=True)
    content_html = models.TextField(blank=True)
    edit_summary = models.CharField(max_length=500, blank=True)

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="article_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    restored_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="restored_to",
    )
    content_hash = models.CharField(max_length=64, editable=False)

    class Meta:
        verbose_name = "версия статьи"
        verbose_name_plural = "версии статей"
        ordering = ["-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "revision_number"],
                name="unique_article_revision_number",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.article.title} — версия №{self.revision_number}"

    def save(self, *args, **kwargs):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content_source.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)


class ArticleRedirect(models.Model):
    """Keeps an old slug working after a rename (section 4.6)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    old_slug = models.SlugField(max_length=255, unique=True, allow_unicode=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="redirects")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = "перенаправление статьи"
        verbose_name_plural = "перенаправления статей"

    def __str__(self) -> str:
        return f"{self.old_slug} → {self.article.slug}"
