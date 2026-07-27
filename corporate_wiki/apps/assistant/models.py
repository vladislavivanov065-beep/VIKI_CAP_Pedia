from __future__ import annotations

from django.conf import settings
from django.db import models


class AssistantSettings(models.Model):
    """Site-wide on/off switch for the AI assistant, controlled by an
    administrator from the sidebar (see apps.assistant.views.toggle).

    A singleton row (see get_solo) rather than a settings.py value,
    because it needs to be flippable at runtime by an admin without a
    redeploy. When disabled, nobody can send a question to OpenAI --
    including someone who already had their own per-question checkbox
    checked, or who tries the endpoint directly.
    """

    is_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    # State of the local (offline, no OpenAI) answer model -- see
    # apps.assistant.training.retrain_local_model. is_training guards
    # against two admins clicking "Переобучить" at once; the counts and
    # timestamp are shown on the admin page so staff can see whether the
    # index is stale relative to the current articles.
    local_ai_is_training = models.BooleanField(default=False)
    local_ai_trained_at = models.DateTimeField(null=True, blank=True)
    local_ai_trained_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    local_ai_article_count = models.PositiveIntegerField(default=0)
    local_ai_chunk_count = models.PositiveIntegerField(default=0)
    local_ai_last_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "настройки ИИ-ассистента"
        verbose_name_plural = "настройки ИИ-ассистента"

    def __str__(self) -> str:
        return "ИИ-ассистент включён" if self.is_enabled else "ИИ-ассистент выключен"

    @classmethod
    def get_solo(cls) -> AssistantSettings:
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class ArticleChunkEmbedding(models.Model):
    """A chunk of an article's plain text plus its embedding vector.

    Built from scratch by apps.assistant.training.retrain_local_model from
    every non-archived article, whenever an administrator clicks
    "Переобучить" -- not kept in sync incrementally, so there's nothing to
    update when an article is edited until the next retrain. Powers
    corpus-wide retrieval for the local ("умный") AI answer mode.
    """

    article = models.ForeignKey(
        "articles.Article", on_delete=models.CASCADE, related_name="chunk_embeddings"
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = models.BinaryField()

    class Meta:
        ordering = ["article_id", "chunk_index"]
        verbose_name = "фрагмент статьи (локальный ИИ)"
        verbose_name_plural = "фрагменты статей (локальный ИИ)"

    def __str__(self) -> str:
        return f"{self.article_id}#{self.chunk_index}"
