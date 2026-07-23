"""Read-only queries for articles and revisions (section 13)."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.models import User
from apps.articles.models import Article, ArticleRevision


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
