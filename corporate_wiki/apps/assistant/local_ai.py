"""Ties corpus-wide retrieval together with local generation into a
single "does the local AI have anything trained yet" answer path. Kept
separate from retrieval/local_models so apps.assistant.services can call
one function and get either a synthesized answer or None (nothing
trained yet, nothing relevant found, generation failed, or the answer
didn't look grounded in what was retrieved) without knowing anything
about embeddings or the generation model itself.
"""

from __future__ import annotations

import logging
import re

from apps.assistant import local_models, retrieval
from apps.assistant.models import ArticleChunkEmbedding

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\w+", re.UNICODE)
# Only words at least this long count towards "grounded" -- short words
# (prepositions, pronouns, etc.) overlap by chance too easily to mean
# anything.
_MIN_MEANINGFUL_WORD_LEN = 4
# Fraction of the answer's meaningful words that must also appear in the
# retrieved context for the answer to be trusted.
_MIN_GROUNDING_OVERLAP = 0.2


def _is_grounded(*, answer: str, context: str) -> bool:
    """A cheap guard against a small model rambling off-topic instead of
    using the retrieved text: the answer should share a real fraction of
    its meaningful words with the context it was supposedly built from.
    Not a rigorous check -- just enough to catch an answer that doesn't
    reference the retrieved article at all, so that case can fall back
    to plain-text search instead of showing something unrelated.
    """
    answer_words = {
        word for word in _WORD_RE.findall(answer.lower()) if len(word) >= _MIN_MEANINGFUL_WORD_LEN
    }
    if not answer_words:
        return True  # too short to judge either way -- don't block it
    context_words = set(_WORD_RE.findall(context.lower()))
    overlap = answer_words & context_words
    return len(overlap) / len(answer_words) >= _MIN_GROUNDING_OVERLAP


def answer_from_corpus(*, question: str) -> str | None:
    if not ArticleChunkEmbedding.objects.exists():
        return None

    try:
        chunks = retrieval.find_relevant_chunks(question=question)
        if not chunks:
            return None

        context = "\n\n".join(f"«{chunk.article.title}»: {chunk.text}" for chunk in chunks)
        answer = local_models.generate_answer(context=context, question=question)
        if not _is_grounded(answer=answer, context=context):
            logger.warning("Local AI answer doesn't overlap with retrieved context -- discarding")
            return None
        return answer
    except Exception:
        logger.exception("Local AI answer generation failed, falling back to text search")
        return None
