"""Rebuilds the local AI's corpus-wide index from every non-archived
article -- the "Переобучить" action on the admin page. A full rebuild
rather than an incremental update: simpler, and cheap enough at the scale
of a corporate wiki that there's no need to track which articles changed
since the last run.

retrain_local_model runs synchronously (used by tests, which want a
completed result to assert on); start_retrain_in_background does the same
work on a daemon thread so the admin's HTTP request returns immediately,
with progress visible on the page via local_ai_log (see
apps.assistant.views.local_ai_status).
"""

from __future__ import annotations

import threading

import numpy as np
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant import local_models
from apps.assistant.models import ArticleChunkEmbedding, AssistantSettings
from apps.assistant.text_utils import article_plain_text, split_sentences

# Chunks are grouped whole sentences, never split mid-sentence, up to this
# many characters -- small enough that each chunk stays about one topic,
# so its embedding isn't diluted by unrelated neighbouring sentences and
# apps.assistant.local_ai's sentence extraction has a focused pool to
# search within.
_CHUNK_CHARS = 400

# Keeps local_ai_log from growing without bound across many retrains.
_MAX_LOG_LINES = 500


class LocalAiAlreadyTrainingError(Exception):
    """Another retrain is already in progress."""


def _chunk_text(text: str, *, chunk_chars: int = _CHUNK_CHARS) -> list[str]:
    sentences = split_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) + 1 > chunk_chars:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _log(solo: AssistantSettings, message: str) -> None:
    timestamp = timezone.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    combined = f"{solo.local_ai_log}\n{line}" if solo.local_ai_log else line
    solo.local_ai_log = "\n".join(combined.splitlines()[-_MAX_LOG_LINES:])
    solo.save(update_fields=["local_ai_log"])


def _begin() -> AssistantSettings:
    solo = AssistantSettings.get_solo()
    if solo.local_ai_is_training:
        raise LocalAiAlreadyTrainingError("Обучение уже выполняется.")

    solo.local_ai_is_training = True
    solo.local_ai_last_error = ""
    solo.local_ai_log = ""
    solo.save(update_fields=["local_ai_is_training", "local_ai_last_error", "local_ai_log"])
    return solo


def _do_training(*, actor: User, solo: AssistantSettings) -> None:
    """Never raises on a model/embedding failure -- records it in
    local_ai_last_error (and the log) instead, so a failed retrain shows
    up as a message on the admin page rather than a 500 or a silently
    dead background thread.
    """
    try:
        _log(solo, "Начало обучения…")
        articles = list(Article.objects.filter(is_archived=False))
        _log(solo, f"Найдено статей: {len(articles)}")

        chunk_rows: list[tuple[Article, int, str]] = []
        for position, article in enumerate(articles, start=1):
            text = article_plain_text(article)
            if not text:
                _log(solo, f"[{position}/{len(articles)}] «{article.title}» — пустая, пропущена")
                continue
            article_chunks = _chunk_text(text)
            for index, chunk in enumerate(article_chunks):
                chunk_rows.append((article, index, chunk))
            _log(
                solo,
                f"[{position}/{len(articles)}] «{article.title}» — {len(article_chunks)} фрагм.",
            )

        embeddings: np.ndarray
        if chunk_rows:
            _log(solo, f"Вычисление эмбеддингов для {len(chunk_rows)} фрагментов…")
            embeddings = local_models.embed_texts([chunk for _article, _index, chunk in chunk_rows])
        else:
            embeddings = np.empty((0,), dtype=np.float32)

        _log(solo, "Запись в базу данных…")
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
        _log(solo, f"Готово: {len(articles)} статей, {len(chunk_rows)} фрагментов.")
    except Exception as exc:  # surfaced via local_ai_last_error, not raised
        solo.local_ai_last_error = str(exc)
        _log(solo, f"Ошибка: {exc}")
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


def retrain_local_model(*, actor: User) -> None:
    """Synchronous entrypoint -- blocks until training finishes or fails.
    Used directly by tests; the admin view uses
    start_retrain_in_background instead so the HTTP request returns
    immediately. Raises LocalAiAlreadyTrainingError if a retrain is
    already running, otherwise never raises (see _do_training).
    """
    solo = _begin()
    _do_training(actor=actor, solo=solo)


def _run_in_background(actor: User, solo: AssistantSettings) -> None:
    try:
        _do_training(actor=actor, solo=solo)
    finally:
        close_old_connections()


def start_retrain_in_background(*, actor: User) -> None:
    """Same guard as retrain_local_model, but the actual work happens on
    a daemon thread so this returns immediately -- the admin page polls
    local_ai_log/local_ai_is_training to show progress live.
    """
    solo = _begin()
    threading.Thread(target=_run_in_background, args=(actor, solo), daemon=True).start()
