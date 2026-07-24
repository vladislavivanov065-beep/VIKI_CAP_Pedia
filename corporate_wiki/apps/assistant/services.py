"""RAG pipeline for "Задай свой вопрос": chunk + embed article content,
retrieve the most relevant chunks for a question via cosine similarity,
and ask the chat model to answer using only those chunks.

Embeddings are recomputed synchronously in a post_save signal
(apps/assistant/signals.py) whenever an article's current revision
changes, so newly added or edited articles become answerable without any
manual step. That call is best-effort: if OpenAI is unreachable or the
feature isn't configured, saving the article must never fail because of
it (see sync_article_embeddings) -- unlike ``answer_question``, which
raises so the person asking a question sees why it didn't work.

Retrieval is a brute-force cosine similarity scan over every chunk in
Python -- the same trade-off apps.articles.similarity documents for
TF-IDF: no vector database, fine at the scale of a single corporate
wiki. No hard relevance-score cutoff is applied; the top few chunks are
always handed to the model, and the system prompt instructs it to say
so plainly when they don't actually answer the question -- a numeric
cosine threshold picked without real traffic to calibrate against would
just be a second, less reliable judge of the same thing.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import re
from array import array
from html import unescape

from django.conf import settings
from django.db import transaction

from apps.articles.models import Article
from apps.assistant import openai_client
from apps.assistant.exceptions import AssistantNotConfiguredError, AssistantRequestError
from apps.assistant.models import ArticleChunk

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_CHUNK_SIZE_CHARS = 1500
_CHUNK_OVERLAP_CHARS = 150
_RETRIEVAL_LIMIT = 5

_SYSTEM_PROMPT = (
    "Ты — ассистент корпоративной базы знаний. Отвечай на вопрос СТРОГО "
    "на основе приведённых ниже фрагментов статей. Если в фрагментах нет "
    "ответа на вопрос, честно скажи, что не нашёл ответ в базе знаний — "
    "не придумывай факты и не используй знания извне. Отвечай кратко и "
    "по делу, на русском языке."
)


def _plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    text = unescape(_TAG_RE.sub(" ", html or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


def _split_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            boundary = text.rfind(". ", start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_article_text(article: Article) -> list[str]:
    """Split an article's plain-text content into overlapping chunks,
    each prefixed with the title for context. Empty for an article with
    no content yet.
    """
    body = _plain_text(article)
    if not body:
        return []
    return [
        f"{article.title}\n\n{part}"
        for part in _split_text(body, chunk_size=_CHUNK_SIZE_CHARS, overlap=_CHUNK_OVERLAP_CHARS)
    ]


def pack_embedding(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack_embedding(data: bytes | memoryview) -> array:
    # SQLite's BinaryField comes back as a memoryview, not bytes.
    vector: array = array("f")
    vector.frombytes(bytes(data))
    return vector


def _cosine_similarity(vector_a, vector_b) -> float:
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)


def sync_article_embeddings(article: Article, *, raise_on_error: bool = False) -> None:
    """Recompute this article's chunks + embeddings from its current
    revision.

    Best-effort by default: any failure (feature not configured, OpenAI
    unreachable, ...) is logged and swallowed rather than raised, since
    this runs synchronously from a signal inside the article-save
    transaction and must never be the reason a save fails. Existing
    chunks are left untouched if embedding generation fails partway
    through, rather than being wiped and leaving the article
    unanswerable. Pass ``raise_on_error=True`` for an explicit,
    deliberate run (the rebuild_embeddings management command) where a
    failure should be reported instead of silently skipped.
    """
    if article.is_archived or article.current_revision_id is None:
        ArticleChunk.objects.filter(article=article).delete()
        return

    if not settings.OPENAI_API_KEY:
        if raise_on_error:
            raise AssistantNotConfiguredError("ИИ-ассистент не настроен: не задан OPENAI_API_KEY.")
        return

    try:
        chunk_texts = chunk_article_text(article)
        new_chunks = [
            ArticleChunk(
                article=article,
                chunk_index=index,
                text=text,
                embedding=pack_embedding(openai_client.create_embedding(text)),
                embedding_model=settings.OPENAI_EMBEDDING_MODEL,
            )
            for index, text in enumerate(chunk_texts)
        ]
    except Exception:
        if raise_on_error:
            raise
        logger.exception("Failed to sync AI-assistant embeddings for article %s", article.pk)
        return

    with transaction.atomic():
        ArticleChunk.objects.filter(article=article).delete()
        ArticleChunk.objects.bulk_create(new_chunks)


@dataclasses.dataclass
class RetrievedChunk:
    chunk: ArticleChunk
    score: float


def find_relevant_chunks(question: str, *, limit: int = _RETRIEVAL_LIMIT) -> list[RetrievedChunk]:
    question_vector = openai_client.create_embedding(question)

    chunks = ArticleChunk.objects.filter(article__is_archived=False).select_related(
        "article", "article__current_revision"
    )
    scored = [
        RetrievedChunk(
            chunk=chunk,
            score=_cosine_similarity(question_vector, unpack_embedding(chunk.embedding)),
        )
        for chunk in chunks
    ]
    scored.sort(key=lambda item: -item.score)
    return scored[:limit]


@dataclasses.dataclass
class AnswerResult:
    answer: str
    sources: list[Article]


def answer_question(question: str) -> AnswerResult:
    question = question.strip()
    if not question:
        raise AssistantRequestError("Введите вопрос.")

    relevant = find_relevant_chunks(question)
    if not relevant:
        return AnswerResult(answer="Не нашёл ответ на этот вопрос в базе знаний.", sources=[])

    context = "\n\n---\n\n".join(item.chunk.text for item in relevant)
    user_prompt = f"Фрагменты статей:\n\n{context}\n\n---\n\nВопрос: {question}"

    answer = openai_client.create_chat_completion(
        system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt
    )

    seen_ids: set = set()
    sources: list[Article] = []
    for item in relevant:
        article = item.chunk.article
        if article.pk not in seen_ids:
            seen_ids.add(article.pk)
            sources.append(article)

    return AnswerResult(answer=answer.strip(), sources=sources)
