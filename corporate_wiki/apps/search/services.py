"""SQLite search: title tiers via plain Django ORM lookups, content
matching (and relevance ranking) via the ``articles_fts`` FTS5 index.

Title matches still go through explicit exact/starts-with/contains tiers
against ``Article.title_normalized`` (already lower-cased in Python at
write time, so this stays correct for Cyrillic without needing SQL-side
case folding) -- a title match is intuitively "more on-topic" by word
position in a way BM25's bag-of-words scoring doesn't capture, and tests
depend on that ordering. Everything past the title tiers -- multi-word
content queries, ranking by relevance, morphological variants via prefix
matching -- is delegated to FTS5, which both solves the Cyrillic
case-folding problem at the DB level (see apps/search/fts.py) and scales
with the index rather than a per-request Python scan over article rows.
"""

from __future__ import annotations

import difflib
import re

from django.db.models import Q, QuerySet
from django.utils.html import escape

from apps.articles.models import Article
from apps.search import fts

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_MIN_SUGGESTION_TOKEN_LENGTH = 3
_SUGGESTION_CUTOFF = 0.72


def _rank_by_tiers(base_qs: QuerySet[Article], tier_filters: list[Q], limit: int) -> list[Article]:
    seen: set = set()
    ranked_ids: list = []

    for tier_filter in tier_filters:
        tier_ids = base_qs.filter(tier_filter).values_list("pk", flat=True)
        for pk in tier_ids:
            if pk not in seen:
                seen.add(pk)
                ranked_ids.append(pk)
        if len(ranked_ids) >= limit:
            break

    ranked_ids = ranked_ids[:limit]
    articles_by_id = base_qs.in_bulk(ranked_ids)
    return [articles_by_id[pk] for pk in ranked_ids if pk in articles_by_id]


def _title_tier_filters(normalized_query: str) -> list[Q]:
    return [
        Q(title_normalized=normalized_query),
        Q(title_normalized__startswith=normalized_query),
    ]


def search_articles(
    query: str, *, include_archived: bool = False, limit: int = 20
) -> list[Article]:
    """Rank matches: exact title, title starts-with, then FTS5
    relevance (BM25) across title-contains and full content.
    """
    query = query.strip()
    if not query:
        return []
    normalized_query = query.lower()

    base_qs = Article.objects.select_related("current_revision", "current_revision__edited_by")
    if not include_archived:
        base_qs = base_qs.filter(is_archived=False)

    ranked = _rank_by_tiers(base_qs, _title_tier_filters(normalized_query), limit)

    if len(ranked) < limit:
        seen_ids = {str(article.pk) for article in ranked}
        hits = fts.search(query, limit=limit * 4)
        remaining_ids = [hit.article_id for hit in hits if hit.article_id not in seen_ids]
        fetched_by_id = {str(a.pk): a for a in base_qs.filter(pk__in=remaining_ids)}
        for article_id in remaining_ids:
            if len(ranked) >= limit:
                break
            article = fetched_by_id.get(article_id)
            if article is not None:
                ranked.append(article)

    return ranked[:limit]


def search_with_snippets(
    query: str, *, include_archived: bool = False, limit: int = 20
) -> list[dict]:
    """``search_articles`` results enriched with a highlighted title and
    content snippet (``<mark>``-wrapped matches, HTML-safe) for the
    results page. Falls back to a plain, unhighlighted excerpt when the
    match was in the title only (nothing in the content to highlight).
    """
    results = []
    for article in search_articles(query, include_archived=include_archived, limit=limit):
        revision = article.current_revision
        snippet = fts.snippet_html(str(article.pk), query)
        if snippet is None:
            plain = extract_snippet(revision.content_source, query) if revision else ""
            snippet = escape(plain)
        results.append({"article": article, "revision": revision, "snippet": snippet})
    return results


def suggest_correction(query: str) -> str | None:
    """A "did you mean" correction built via fuzzy-matching each query
    token against the FTS index's own vocabulary -- ``None`` if the query
    already matches known words, or no close-enough word exists.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(query)]
    if not tokens:
        return None

    vocabulary = fts.vocabulary()
    if not vocabulary:
        return None

    corrected = []
    changed = False
    for token in tokens:
        if len(token) < _MIN_SUGGESTION_TOKEN_LENGTH or token in vocabulary:
            corrected.append(token)
            continue
        matches = difflib.get_close_matches(token, vocabulary, n=1, cutoff=_SUGGESTION_CUTOFF)
        if matches:
            corrected.append(matches[0])
            changed = True
        else:
            corrected.append(token)

    return " ".join(corrected) if changed else None


def search_suggestions(query: str, *, limit: int = 10) -> list[Article]:
    """Title-only ranking for the search-box autocomplete (section 8.4)."""
    query = query.strip()
    if len(query) < 2:
        return []
    normalized_query = query.lower()

    base_qs = Article.objects.filter(is_archived=False)
    return _rank_by_tiers(
        base_qs,
        [
            Q(title_normalized=normalized_query),
            Q(title_normalized__startswith=normalized_query),
            Q(title_normalized__contains=normalized_query),
        ],
        limit,
    )


def extract_snippet(content: str, query: str, *, context_chars: int = 80) -> str:
    """A short excerpt around the first match, for the results list."""
    if not content:
        return ""

    lowered = content.lower()
    query_lowered = query.strip().lower()
    index = lowered.find(query_lowered) if query_lowered else -1

    if index == -1:
        snippet = content[: context_chars * 2]
        return snippet + ("…" if len(content) > len(snippet) else "")

    start = max(0, index - context_chars)
    end = min(len(content), index + len(query_lowered) + context_chars)
    snippet = content[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet
