from __future__ import annotations

import uuid

from django.db import models

from apps.articles.models import Article


class ArticleChunk(models.Model):
    """One indexed slice of an article's text, with its embedding vector,
    used to answer questions in the "Задай свой вопрос" panel.

    Articles are split into chunks (see apps.assistant.services.
    chunk_article_text) rather than embedded whole, so retrieval can point
    at the specific passage that actually answers a question instead of
    an entire (possibly long) article, and so a single article doesn't
    blow the embedding model's input size.

    Kept in sync with the article's current revision via a post_save
    signal (apps/assistant/signals.py) -- the whole point of this table
    is that newly added or edited articles become answerable without any
    manual step.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    # A packed array('f', ...) of floats (see services.py pack_embedding/
    # unpack_embedding) -- far more compact than storing the vector as
    # JSON text, and no numpy/vector-DB dependency needed to read it back.
    embedding = models.BinaryField()
    embedding_model = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "фрагмент статьи для ИИ-поиска"
        verbose_name_plural = "фрагменты статей для ИИ-поиска"
        ordering = ["article", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "chunk_index"], name="unique_article_chunk_index"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.article.title} — фрагмент {self.chunk_index}"
