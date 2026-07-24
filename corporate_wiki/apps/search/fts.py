"""SQLite FTS5-backed full-text index for articles.

Raw SQL against the ``articles_fts``/``articles_fts_vocab`` virtual tables
created in ``0001_initial`` -- there is no Django model for them (FTS5's
efficient content mode needs an integer rowid-compatible primary key,
which ``Article.id`` isn't, see that migration's comment).

Every query token is issued as an FTS5 *prefix* query (``"term"*``)
rather than an exact-token match. FTS5 has no stemmer for Russian, so an
exact match on "отпуск" would miss "отпуска"/"отпускные"/etc; prefix
matching against the token stem approximates that for the common case
where Russian declension/conjugation only adds a suffix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape

from django.db import connection

FTS_TABLE = "articles_fts"
VOCAB_TABLE = "articles_fts_vocab"

_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

_HIGHLIGHT_BEFORE = "\x01"
_HIGHLIGHT_AFTER = "\x02"


def _plain_text(content_html: str) -> str:
    # Undo the HTML-entity escaping so the index (and its derived vocabulary)
    # stores real words, not artifacts like "lt"/"amp" from stray "&lt;"/"&amp;"
    # in the source markup. snippet_html()/highlight_title_html() re-escape
    # this plain text before it goes back into an HTML response.
    return unescape(_TAG_RE.sub(" ", content_html or ""))


def _tokenize(query: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(query)]


def _match_expression(query: str) -> str:
    tokens = _tokenize(query)
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"*' for token in tokens)


def index_article(article) -> None:
    """Upsert an article's title/content into the FTS index."""
    revision = article.current_revision
    content = _plain_text(revision.content_html if revision else "")
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {FTS_TABLE} WHERE article_id = %s", [str(article.pk)])
        cursor.execute(
            f"INSERT INTO {FTS_TABLE} (article_id, title, content) VALUES (%s, %s, %s)",
            [str(article.pk), article.title, content],
        )


def remove_article(article_id) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {FTS_TABLE} WHERE article_id = %s", [str(article_id)])


def rebuild_index() -> int:
    """Drop and rebuild the whole index from the current article table.

    Existing articles are kept in sync incrementally via a post_save
    signal (apps/search/apps.py); this is for the initial backfill and
    for manual recovery if the index and the article table ever drift.
    """
    from apps.articles.models import Article

    articles = Article.objects.select_related("current_revision").exclude(
        current_revision__isnull=True
    )
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {FTS_TABLE}")
        rows = [
            (str(article.pk), article.title, _plain_text(article.current_revision.content_html))
            for article in articles
            if article.current_revision is not None
        ]
        cursor.executemany(
            f"INSERT INTO {FTS_TABLE} (article_id, title, content) VALUES (%s, %s, %s)", rows
        )
    return len(rows)


@dataclass
class SearchHit:
    article_id: str
    score: float


def search(query: str, *, limit: int = 50) -> list[SearchHit]:
    """Article ids ranked best-first by BM25 relevance across title+content."""
    match_expression = _match_expression(query)
    if not match_expression:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT article_id, bm25({FTS_TABLE}, 0.0, 5.0, 1.0) AS score
            FROM {FTS_TABLE}
            WHERE {FTS_TABLE} MATCH %s
            ORDER BY score
            LIMIT %s
            """,
            [match_expression, limit],
        )
        return [SearchHit(article_id=row[0], score=row[1]) for row in cursor.fetchall()]


def snippet_html(article_id: str, query: str, *, max_tokens: int = 24) -> str | None:
    """A short HTML excerpt around the best content match, matches wrapped
    in ``<mark>``. ``None`` if this article's content doesn't actually
    match the query (e.g. it only matched on title).
    """
    from django.utils.html import escape

    match_expression = _match_expression(query)
    if not match_expression:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT snippet({FTS_TABLE}, 2, %s, %s, '…', %s)
            FROM {FTS_TABLE}
            WHERE {FTS_TABLE} MATCH %s AND article_id = %s
            """,
            [_HIGHLIGHT_BEFORE, _HIGHLIGHT_AFTER, max_tokens, match_expression, article_id],
        )
        row = cursor.fetchone()
    # The row can match overall (e.g. the title matched) while this
    # specific column has no match of its own -- snippet() then just
    # returns an arbitrary excerpt with no highlight markers in it, which
    # isn't a "match" worth showing here.
    if row is None or _HIGHLIGHT_BEFORE not in row[0]:
        return None
    escaped = escape(row[0])
    return escaped.replace(_HIGHLIGHT_BEFORE, "<mark>").replace(_HIGHLIGHT_AFTER, "</mark>")


def vocabulary() -> set[str]:
    """The distinct set of indexed terms, for spelling suggestions."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT term FROM {VOCAB_TABLE}")
        return {row[0] for row in cursor.fetchall()}
