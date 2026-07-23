"""Read-only queries for articles and revisions (section 13)."""

from __future__ import annotations

import re

from django.db.models import QuerySet

from apps.accounts.models import User
from apps.articles.models import Article, ArticleRevision

_TAG_RE = re.compile(r"<[^>]+>")
_SIDEBAR_LIST_SCAN_LIMIT = 2000
_SIDEBAR_LIST_RESULT_LIMIT = 300


def get_article_by_slug(slug: str, *, include_archived: bool = False) -> Article:
    qs = Article.objects.all()
    if not include_archived:
        qs = qs.filter(is_archived=False)
    return qs.get(slug=slug)


def get_article_history(article: Article) -> QuerySet[ArticleRevision]:
    return article.revisions.select_related("edited_by", "restored_from").order_by(
        "-revision_number"
    )


def get_revision(article: Article, revision_number: int) -> ArticleRevision:
    return article.revisions.select_related("edited_by").get(revision_number=revision_number)


def get_recent_articles(*, limit: int = 10) -> QuerySet[Article]:
    return Article.objects.filter(is_archived=False).order_by("-updated_at")[:limit]


def get_user_contributions(user: User, *, limit: int | None = None) -> QuerySet[ArticleRevision]:
    qs = (
        ArticleRevision.objects.filter(edited_by=user)
        .select_related("article")
        .order_by("-created_at")
    )
    return qs[:limit] if limit else qs


def find_articles_for_sidebar_list(query: str = "") -> list[Article]:
    """Backs the sidebar's quick-browse/quick-search widget: all active
    article titles when ``query`` is blank, or every article whose title
    or content contains *all* the given words (matched in Python, not
    SQL — SQLite's ``LOWER()``/``LIKE`` only case-fold ASCII, so a
    Cyrillic-aware substring match has to happen here; see
    apps/search/services.py for the same constraint).
    """
    base_qs = (
        Article.objects.filter(is_archived=False)
        .select_related("current_revision")
        .order_by("title")
    )

    query = query.strip()
    if not query:
        return list(base_qs[:_SIDEBAR_LIST_RESULT_LIMIT])

    words = [word for word in query.lower().split() if word]
    if not words:
        return list(base_qs[:_SIDEBAR_LIST_RESULT_LIMIT])

    matched: list[Article] = []
    for article in base_qs[:_SIDEBAR_LIST_SCAN_LIMIT]:
        haystack = article.title.lower()
        if article.current_revision:
            haystack += " " + _TAG_RE.sub(" ", article.current_revision.content_html or "").lower()
        if all(word in haystack for word in words):
            matched.append(article)
            if len(matched) >= _SIDEBAR_LIST_RESULT_LIMIT:
                break
    return matched
