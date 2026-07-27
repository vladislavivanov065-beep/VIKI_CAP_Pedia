"""Ties corpus-wide semantic retrieval together with sentence-level
extraction into a single "does the local AI have anything trained yet"
answer path. Kept separate from retrieval/local_search so
apps.assistant.services can call one function and get either an answer
or None (nothing trained yet, or nothing relevant found) without knowing
anything about embeddings.

Deliberately extractive, not generative: a small local instruct model
was tried here and reliably either hallucinated (answered from unrelated
words instead of the retrieved text) or just echoed the retrieved
fragments back wholesale instead of summarizing them, neither of which
beats returning the actual matching sentence. The "neural network" doing
the "thinking" is the embedding model finding the right sentence out of
every article -- not a generator making prose out of it.
"""

from __future__ import annotations

import logging

from apps.assistant import local_search, retrieval
from apps.assistant.models import ArticleChunkEmbedding

logger = logging.getLogger(__name__)


def answer_from_corpus(*, question: str) -> str | None:
    if not ArticleChunkEmbedding.objects.exists():
        return None

    try:
        chunks = retrieval.find_relevant_chunks(question=question, top_k=1)
        if not chunks:
            return None

        best_chunk = chunks[0]
        sentences = local_search.find_best_sentences(
            text=best_chunk.text, question=question, max_sentences=1
        )
        return sentences[0] if sentences else best_chunk.text
    except Exception:
        logger.exception("Local AI extraction failed, falling back to text search")
        return None
