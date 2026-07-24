"""Read-only queries for articles and revisions (section 13)."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import User
from apps.articles.models import Article, ArticleRevision
from apps.search import fts

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
    or content matches *all* the given words -- via the FTS5 index
    (apps/search/fts.py) rather than a per-row Python scan, so this stays
    fast as the article count grows and is Cyrillic-case-insensitive at
    the DB level.
    """
    base_qs = (
        Article.objects.filter(is_archived=False)
        .select_related("current_revision")
        .order_by("title")
    )

    query = query.strip()
    if not query:
        return list(base_qs[:_SIDEBAR_LIST_RESULT_LIMIT])

    hits = fts.search(query, limit=_SIDEBAR_LIST_RESULT_LIMIT)
    if not hits:
        return []

    ids = [hit.article_id for hit in hits]
    fetched_by_id = {str(a.pk): a for a in base_qs.filter(pk__in=ids)}
    return [fetched_by_id[article_id] for article_id in ids if article_id in fetched_by_id]
