"""Ties an article's semantic retrieval together with cross-encoder
reranking into a single "does the local AI have anything trained yet"
answer path. Kept separate from retrieval/local_search so
apps.assistant.services can call one function and get either an answer or
None (nothing trained yet, or nothing relevant found) without knowing
anything about embeddings.

Scoped to a single article -- see apps.assistant.retrieval -- so a
question asked on one article's page is only ever answered from that
article's own text, never from some other article in the corpus.

Deliberately extractive, not generative: a small local instruct model was
tried here and reliably either hallucinated (answered from unrelated words
instead of the retrieved text) or just echoed the retrieved fragments back
wholesale instead of summarizing them, neither of which beats returning
the actual matching sentence. The "neural network" doing the "thinking" is
the embedding model finding the right sentence within the article -- not
a generator making prose out of it.

Each row in the index is one semantically coherent fragment (see
apps.assistant.training/chunking), so retrieval already returns
fragment-sized candidates; the top embedding match alone is sometimes not
the best-worded one though, so the top _CANDIDATE_POOL_SIZE candidates are
reranked by a cross-encoder (apps.assistant.local_models.score_pairs),
which judges the question and a candidate together rather than comparing
separately computed representations -- a better judge of "does this
answer the question" than cosine similarity or keyword overlap alone.
Falls back to lemmatized keyword overlap (local_search.pick_best_sentence)
if the cross-encoder fails to load/run for any reason.

When even the winning candidate's cross-encoder score is low, the runner-
up candidates are surfaced as alternatives rather than silently discarded
-- see AnswerFromArticle -- so a caller can show "possibly also relevant"
options instead of presenting a shaky pick as the definitive answer.
"""

from __future__ import annotations

import dataclasses
import logging

from apps.articles.models import Article
from apps.assistant import local_models, local_search, retrieval
from apps.assistant.models import ArticleChunkEmbedding

logger = logging.getLogger(__name__)

_CANDIDATE_POOL_SIZE = 5
# Cross-encoder scores are in [0, 1]; below this, the winning candidate is
# treated as a shaky guess rather than a confident answer, and runner-up
# candidates are surfaced alongside it instead of presenting it alone.
_LOW_CONFIDENCE_THRESHOLD = 0.5
_MAX_ALTERNATIVES = 2
# Added to a candidate's cross-encoder score when it contains, verbatim, a
# number/code token (BIN, tariff, limit) that also appears in the question
# -- see local_search.exact_match_bonus. Deliberately small: this is a
# tiebreaker between semantically similar candidates, not something that
# should override a clearly better semantic match elsewhere in the pool.
_EXACT_MATCH_BONUS_WEIGHT = 0.1


@dataclasses.dataclass
class AnswerFromArticle:
    text: str
    alternatives: list[str] = dataclasses.field(default_factory=list)


def answer_from_article(*, question: str, article: Article) -> AnswerFromArticle | None:
    if not ArticleChunkEmbedding.objects.filter(article=article).exists():
        return None

    try:
        candidates = retrieval.find_relevant_chunks(
            question=question, article=article, top_k=_CANDIDATE_POOL_SIZE
        )
        if not candidates:
            return None

        sentences = [candidate.text for candidate in candidates]
        return _rank_candidates(sentences=sentences, question=question)
    except Exception:
        logger.exception("Local AI extraction failed, falling back to text search")
        return None


def _rank_candidates(*, sentences: list[str], question: str) -> AnswerFromArticle:
    try:
        scores = local_models.score_pairs(question=question, candidates=sentences)
        bonuses = local_search.exact_match_bonus(question=question, candidates=sentences)
        boosted_scores = [
            score + bonus * _EXACT_MATCH_BONUS_WEIGHT
            for score, bonus in zip(scores, bonuses, strict=True)
        ]
        ranked = sorted(range(len(sentences)), key=lambda i: boosted_scores[i], reverse=True)
        best_index = ranked[0]

        alternatives: list[str] = []
        if boosted_scores[best_index] < _LOW_CONFIDENCE_THRESHOLD:
            alternatives = [sentences[i] for i in ranked[1 : 1 + _MAX_ALTERNATIVES]]
        return AnswerFromArticle(text=sentences[best_index], alternatives=alternatives)
    except Exception:
        logger.exception("Cross-encoder reranking failed, falling back to keyword overlap")
        best = local_search.pick_best_sentence(sentences=sentences, question=question)
        return AnswerFromArticle(text=best if best is not None else sentences[0])
