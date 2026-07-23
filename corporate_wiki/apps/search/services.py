"""SQLite-only search (section 8.2).

Deliberately built on plain Django ORM lookups — no PostgreSQL full-text
search, no ``SearchVector``/``SearchQuery``/``SearchRank``, no GIN
indexes. Ranking is done in Python by running the query once per tier
(exact title, title starts-with, title contains, content contains) and
merging results in that priority order, exactly as the spec describes.

Title tiers match against ``Article.title_normalized`` (already
lower-cased in Python at write time) rather than using ``__iexact`` /
``__istartswith`` / ``__icontains`` directly on ``title``: SQLite's
built-in ``LIKE``/``LOWER`` only case-fold ASCII, so a case-insensitive
match against Cyrillic text silently fails otherwise. The content tier
has no such pre-normalized field, so it's matched in Python instead —
explicitly sanctioned by section 8.2 ("ранжировать на уровне Python").
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.articles.models import Article

_CONTENT_TIER_SCAN_LIMIT = 500


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
        Q(title_normalized__contains=normalized_query),
    ]


def search_articles(
    query: str, *, include_archived: bool = False, limit: int = 20
) -> list[Article]:
    """Rank matches: exact title, title starts-with, title contains, then
    current-revision content contains (section 8.2's four tiers).
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
        seen_ids = {article.pk for article in ranked}
        candidates = (
            base_qs.exclude(pk__in=seen_ids)
            .exclude(current_revision__isnull=True)
            .select_related("current_revision")[:_CONTENT_TIER_SCAN_LIMIT]
        )
        for article in candidates:
            if len(ranked) >= limit:
                break
            revision = article.current_revision
            if revision is None:
                continue
            if normalized_query in revision.content_source.lower():
                ranked.append(article)

    return ranked[:limit]


def search_suggestions(query: str, *, limit: int = 10) -> list[Article]:
    """Title-only ranking for the search-box autocomplete (section 8.4)."""
    query = query.strip()
    if len(query) < 2:
        return []
    normalized_query = query.lower()

    base_qs = Article.objects.filter(is_archived=False)
    return _rank_by_tiers(base_qs, _title_tier_filters(normalized_query), limit)


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
