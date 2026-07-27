"""Rebuilds the local AI's corpus-wide index from every non-archived
article -- the "Переобучить" action on the admin page. A full rebuild
rather than an incremental update: simpler, and cheap enough at the scale
of a corporate wiki that there's no need to track which articles changed
since the last run.
"""

from __future__ import annotations

import numpy as np
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant import local_models
from apps.assistant.models import ArticleChunkEmbedding, AssistantSettings
from apps.assistant.text_utils import article_plain_text

# Small enough that a tiny local embedding model can encode each chunk
# meaningfully, large enough to give the generator real context per hit.
_CHUNK_CHARS = 800


class LocalAiAlreadyTrainingError(Exception):
    """Another retrain is already in progress."""


def _chunk_text(text: str, *, chunk_chars: int = _CHUNK_CHARS) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_chars:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        chunks.append(" ".join(current))
    return chunks


def retrain_local_model(*, actor: User) -> None:
    """Deletes and recomputes every ArticleChunkEmbedding. Never raises on
    a model/embedding failure -- records it in local_ai_last_error instead,
    so a failed retrain shows up as a message on the admin page rather
    than a 500. Only raises if a retrain is already running.
    """
    solo = AssistantSettings.get_solo()
    if solo.local_ai_is_training:
        raise LocalAiAlreadyTrainingError("Обучение уже выполняется.")

    solo.local_ai_is_training = True
    solo.local_ai_last_error = ""
    solo.save(update_fields=["local_ai_is_training", "local_ai_last_error"])

    try:
        articles = list(Article.objects.filter(is_archived=False))

        chunk_rows: list[tuple[Article, int, str]] = []
        for article in articles:
            text = article_plain_text(article)
            if not text:
                continue
            for index, chunk in enumerate(_chunk_text(text)):
                chunk_rows.append((article, index, chunk))

        embeddings: np.ndarray
        if chunk_rows:
            embeddings = local_models.embed_texts([chunk for _article, _index, chunk in chunk_rows])
        else:
            embeddings = np.empty((0,), dtype=np.float32)

        with transaction.atomic():
            ArticleChunkEmbedding.objects.all().delete()
            ArticleChunkEmbedding.objects.bulk_create(
                ArticleChunkEmbedding(
                    article=article,
                    chunk_index=index,
                    text=chunk,
                    embedding=embedding.tobytes(),
                )
                for (article, index, chunk), embedding in zip(chunk_rows, embeddings, strict=True)
            )

        solo.local_ai_trained_at = timezone.now()
        solo.local_ai_trained_by = actor
        solo.local_ai_article_count = len(articles)
        solo.local_ai_chunk_count = len(chunk_rows)
        solo.local_ai_last_error = ""
    except Exception as exc:  # surfaced via local_ai_last_error, not raised
        solo.local_ai_last_error = str(exc)
    finally:
        solo.local_ai_is_training = False
        solo.save(
            update_fields=[
                "local_ai_is_training",
                "local_ai_trained_at",
                "local_ai_trained_by",
                "local_ai_article_count",
                "local_ai_chunk_count",
                "local_ai_last_error",
            ]
        )
