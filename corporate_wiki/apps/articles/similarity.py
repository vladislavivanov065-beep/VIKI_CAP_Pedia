""" "Recommended articles" — lightweight topic similarity (no external
search engine, no ML library, no network calls).

Scores every other active article against the current one with TF-IDF
weighted cosine similarity, computed in pure Python and recomputed on
each request. This is a deliberate v1 trade-off: it avoids a new
dependency and a persistent index, and is fast enough at the scale of a
single corporate wiki (low thousands of articles at most). If the
article count ever grows large enough for this to matter, the next step
would be precomputing/caching vectors rather than switching approach.

Tokenizing must happen in Python, not via SQL ``LOWER()``/``LIKE`` —
SQLite's built-in case folding is ASCII-only, so it silently breaks on
Cyrillic text (see apps/search/services.py for the same constraint).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from apps.articles.models import Article

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_TAG_RE = re.compile(r"<[^>]+>")

# A short, deliberately non-exhaustive stopword list (Russian + English) —
# just enough to keep the most common function words from swamping the
# similarity score.
_STOPWORDS = {
    "и",
    "в",
    "во",
    "не",
    "что",
    "он",
    "на",
    "я",
    "с",
    "со",
    "как",
    "а",
    "то",
    "все",
    "она",
    "так",
    "его",
    "но",
    "да",
    "ты",
    "к",
    "у",
    "же",
    "вы",
    "за",
    "бы",
    "по",
    "только",
    "ее",
    "мне",
    "было",
    "вот",
    "от",
    "меня",
    "еще",
    "нет",
    "о",
    "из",
    "ему",
    "теперь",
    "когда",
    "даже",
    "ну",
    "вдруг",
    "ли",
    "если",
    "уже",
    "или",
    "ни",
    "быть",
    "был",
    "него",
    "до",
    "вас",
    "нибудь",
    "опять",
    "уж",
    "вам",
    "ведь",
    "там",
    "потом",
    "себя",
    "ничего",
    "ей",
    "может",
    "они",
    "тут",
    "где",
    "есть",
    "надо",
    "ней",
    "для",
    "мы",
    "тебя",
    "их",
    "чем",
    "была",
    "сам",
    "чтобы",
    "без",
    "будто",
    "чего",
    "раз",
    "тоже",
    "себе",
    "под",
    "будет",
    "тогда",
    "кто",
    "этот",
    "того",
    "потому",
    "этого",
    "какой",
    "совсем",
    "ним",
    "здесь",
    "этом",
    "один",
    "почти",
    "мой",
    "тем",
    "нее",
    "сейчас",
    "были",
    "куда",
    "зачем",
    "всех",
    "никогда",
    "можно",
    "при",
    "наконец",
    "два",
    "об",
    "другой",
    "хоть",
    "после",
    "над",
    "больше",
    "тот",
    "через",
    "эти",
    "нас",
    "про",
    "всего",
    "них",
    "какая",
    "много",
    "три",
    "эту",
    "моя",
    "впрочем",
    "хорошо",
    "свою",
    "этой",
    "перед",
    "иногда",
    "лучше",
    "чуть",
    "том",
    "нельзя",
    "такой",
    "им",
    "более",
    "всегда",
    "конечно",
    "всю",
    "между",
    "также",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "is",
    "are",
    "was",
    "were",
    "with",
    "as",
    "by",
    "at",
    "from",
    "this",
    "that",
    "it",
    "be",
    "have",
    "has",
    "not",
}


def _plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    return f"{article.title}\n{_TAG_RE.sub(' ', html or '')}"


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in (match.group(0).lower() for match in _TOKEN_RE.finditer(text))
        if len(token) > 2 and token not in _STOPWORDS
    ]


def _inverse_document_frequencies(documents: dict[str, Counter[str]]) -> dict[str, float]:
    doc_count = len(documents)
    doc_counts_per_term: Counter[str] = Counter()
    for term_frequencies in documents.values():
        doc_counts_per_term.update(term_frequencies.keys())
    return {
        term: math.log((1 + doc_count) / (1 + doc_count_for_term)) + 1
        for term, doc_count_for_term in doc_counts_per_term.items()
    }


def _tfidf_vector(term_frequencies: Counter[str], idf: dict[str, float]) -> dict[str, float]:
    total = sum(term_frequencies.values()) or 1
    return {term: (count / total) * idf.get(term, 0.0) for term, count in term_frequencies.items()}


def _cosine_similarity(vector_a: dict[str, float], vector_b: dict[str, float]) -> float:
    shared_terms = vector_a.keys() & vector_b.keys()
    if not shared_terms:
        return 0.0
    dot_product = sum(vector_a[term] * vector_b[term] for term in shared_terms)
    magnitude_a = math.sqrt(sum(value * value for value in vector_a.values()))
    magnitude_b = math.sqrt(sum(value * value for value in vector_b.values()))
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    return dot_product / (magnitude_a * magnitude_b)


def find_similar_articles(article: Article, *, limit: int = 3) -> list[Article]:
    """Top ``limit`` other active articles ranked by similarity to
    ``article``. Returns fewer than ``limit`` if there aren't enough
    other articles, and an empty list once nothing shares any
    meaningful term with ``article`` (a zero score is excluded rather
    than padded with unrelated articles).
    """
    target_tokens = _tokenize(_plain_text(article))
    if not target_tokens:
        return []

    others = list(
        Article.objects.filter(is_archived=False)
        .exclude(pk=article.pk)
        .select_related("current_revision")
    )
    if not others:
        return []

    documents: dict[str, Counter[str]] = {"__target__": Counter(target_tokens)}
    for other in others:
        documents[str(other.pk)] = Counter(_tokenize(_plain_text(other)))

    idf = _inverse_document_frequencies(documents)
    target_vector = _tfidf_vector(documents["__target__"], idf)

    scored: list[tuple[float, Article]] = []
    for other in others:
        other_vector = _tfidf_vector(documents[str(other.pk)], idf)
        score = _cosine_similarity(target_vector, other_vector)
        if score > 0:
            scored.append((score, other))

    scored.sort(key=lambda pair: (-pair[0], pair[1].title))
    return [candidate for _score, candidate in scored[:limit]]
