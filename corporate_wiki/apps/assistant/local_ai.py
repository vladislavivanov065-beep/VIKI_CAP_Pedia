"""Ties corpus-wide retrieval together with local generation into a
single "does the local AI have anything trained yet" answer path. Kept
separate from retrieval/local_models so apps.assistant.services can call
one function and get either a synthesized answer or None (nothing
trained yet, nothing relevant found, or the model failed to load) without
knowing anything about embeddings or the generation model itself.
"""

from __future__ import annotations

import logging

from apps.assistant import local_models, retrieval
from apps.assistant.models import ArticleChunkEmbedding

logger = logging.getLogger(__name__)


def answer_from_corpus(*, question: str) -> str | None:
    if not ArticleChunkEmbedding.objects.exists():
        return None

    try:
        chunks = retrieval.find_relevant_chunks(question=question)
        if not chunks:
            return None

        context = "\n\n".join(f"«{chunk.article.title}»: {chunk.text}" for chunk in chunks)
        return local_models.generate_answer(context=context, question=question)
    except Exception:
        logger.exception("Local AI answer generation failed, falling back to text search")
        return None
