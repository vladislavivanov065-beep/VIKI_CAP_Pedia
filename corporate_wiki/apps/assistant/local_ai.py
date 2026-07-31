"""Ties corpus-wide semantic retrieval together with lexical reranking into
a single "does the local AI have anything trained yet" answer path. Kept
separate from retrieval/local_search so apps.assistant.services can call
one function and get either an answer or None (nothing trained yet, or
nothing relevant found) without knowing anything about embeddings.

Deliberately extractive, not generative: a small local instruct model was
tried here and reliably either hallucinated (answered from unrelated words
instead of the retrieved text) or just echoed the retrieved fragments back
wholesale instead of summarizing them, neither of which beats returning
the actual matching sentence. The "neural network" doing the "thinking" is
the embedding model finding the right sentence out of every article -- not
a generator making prose out of it.

Each row in the index is a single sentence (see apps.assistant.training),
so retrieval already returns sentence-sized candidates; the top embedding
match alone is sometimes not the best-worded one though, so the top
_CANDIDATE_POOL_SIZE candidates are reranked by lemmatized keyword overlap
(apps.assistant.local_search.pick_best_sentence) and only fall back to the
plain top embedding match when none of them share a meaningful word with
the question at all.
"""

from __future__ import annotations

import logging

from apps.assistant import local_search, retrieval
from apps.assistant.models import ArticleChunkEmbedding

logger = logging.getLogger(__name__)

_CANDIDATE_POOL_SIZE = 5


def answer_from_corpus(*, question: str) -> str | None:
    if not ArticleChunkEmbedding.objects.exists():
        return None

    try:
        candidates = retrieval.find_relevant_chunks(question=question, top_k=_CANDIDATE_POOL_SIZE)
        if not candidates:
            return None

        sentences = [candidate.text for candidate in candidates]
        best = local_search.pick_best_sentence(sentences=sentences, question=question)
        return best if best is not None else sentences[0]
    except Exception:
        logger.exception("Local AI extraction failed, falling back to text search")
        return None
