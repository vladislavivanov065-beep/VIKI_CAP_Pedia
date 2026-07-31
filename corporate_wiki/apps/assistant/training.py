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

import logging
import threading
import uuid

import numpy as np
from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant import chunking, chunking_remote, local_models
from apps.assistant.models import ArticleChunkEmbedding, AssistantSettings
from apps.assistant.text_utils import article_plain_text

logger = logging.getLogger(__name__)

# Keeps local_ai_log from growing without bound across many retrains.
_MAX_LOG_LINES = 500


class LocalAiAlreadyTrainingError(Exception):
    """Another retrain is already in progress."""


def _chunk_text(text: str) -> list[str]:
    """One row per semantically coherent group of lines -- finer than a
    ~400-character multi-paragraph group (that diluted an embedding
    across several unrelated topics), but coarser than one row per
    physical line: a multi-line block like a billing address, or a
    paragraph introducing a list, stays one retrievable unit instead of
    being split apart at every line break.

    Prefers ChatGPT's grouping (apps.assistant.chunking_remote) when
    OpenAI is configured and the assistant is enabled -- it only ever sees
    redacted line numbers, never the real text (see
    apps.assistant.redaction) -- and falls back to the local
    embedding-based heuristic (apps.assistant.chunking) otherwise, same as
    every other OpenAI-optional path in this app.
    """
    remote_chunks = chunking_remote.remote_group_into_chunks(text)
    if remote_chunks is not None:
        return remote_chunks
    return chunking.group_into_chunks(text)


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


def sync_article_embeddings(article: Article) -> None:
    """Recomputes just this one article's sentence embeddings in place --
    called automatically after every save (see apps.assistant.signals) so
    an edit is searchable right away, without an admin having to click
    "Переобучить" for it. A full retrain is still needed after switching
    LOCAL_AI_EMBEDDING_MODEL (the whole index is in the old model's vector
    space) or to backfill articles that existed before this ever ran.

    An archived article (or one with no text) ends up with no rows, same
    as a full retrain would leave it -- retrieval already excludes
    archived articles by query, but there is no reason to keep stale
    embeddings for one around either.
    """
    sentences = [] if article.is_archived else _chunk_text(article_plain_text(article))
    embeddings = (
        local_models.embed_texts(sentences) if sentences else np.empty((0,), dtype=np.float32)
    )

    with transaction.atomic():
        ArticleChunkEmbedding.objects.filter(article=article).delete()
        ArticleChunkEmbedding.objects.bulk_create(
            ArticleChunkEmbedding(
                article=article,
                chunk_index=index,
                text=sentence,
                embedding=embedding.tobytes(),
            )
            for index, (sentence, embedding) in enumerate(zip(sentences, embeddings, strict=True))
        )


def _run_sync_article_embeddings_in_background(article_id: uuid.UUID) -> None:
    try:
        article = Article.objects.get(pk=article_id)
        sync_article_embeddings(article)
    except Article.DoesNotExist:
        pass
    except Exception:
        logger.exception("Local AI incremental sync failed for article %s", article_id)
    finally:
        close_old_connections()


def start_sync_article_embeddings_in_background(article_id: uuid.UUID) -> None:
    """No-op until the index has been built at least once -- an install
    that has never used the local AI feature (never clicked "Переобучить")
    shouldn't have every article save start downloading/loading an ML
    model just to maintain an index nobody queries.
    """
    if not AssistantSettings.get_solo().local_ai_trained_at:
        return
    threading.Thread(
        target=_run_sync_article_embeddings_in_background, args=(article_id,), daemon=True
    ).start()
