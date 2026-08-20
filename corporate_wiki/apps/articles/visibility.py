"""Department-based access control for articles: an article restricted
to specific departments (Article.visible_departments) is only visible to
a user whose own department (User.department) is one of them.

An article with NO departments selected is unrestricted -- visible to
everyone, including a user with no department of their own -- so nothing
already published silently disappeared the moment this feature shipped;
restricting an article is an explicit opt-in per article, not a default.

Staff bypass this entirely and always see every article, same as every
other admin-only capability already in this app (archiving, restoring a
revision, and so on) -- an administrator managing the wiki isn't cut off
by their own department assignment (or lack of one).
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.articles.models import Article


def visibility_filter(user: User, *, prefix: str = "") -> Q:
    """A Q object matching visible articles -- the piece `visible_articles`
    below is built from, exposed separately for a queryset of some OTHER
    model with a relation to Article, via `prefix` (e.g.
    "related_article__" for apps.articles.similarity's ArticleSimilarity
    cache). Matches everything when `user` is staff.
    """
    if user.is_staff:
        return Q()
    field = f"{prefix}visible_departments"
    matches = Q(**{f"{field}__isnull": True})
    if user.department_id:
        matches |= Q(**{field: user.department_id})
    return matches


def visible_articles(user: User, queryset: QuerySet[Article] | None = None) -> QuerySet[Article]:
    """Narrows `queryset` (defaults to every article, archived included --
    callers filter is_archived themselves, same as every other selector
    in this app) down to the ones `user` is allowed to see.
    """
    queryset = Article.objects.all() if queryset is None else queryset
    return queryset.filter(visibility_filter(user)).distinct()


def article_is_visible(article: Article, user: User) -> bool:
    """Single-article check for a caller that already has the Article
    instance loaded (e.g. after a slug lookup) -- see visible_articles
    for the queryset-level equivalent used by list/search views.
    """
    if user.is_staff:
        return True
    department_ids = set(article.visible_departments.values_list("id", flat=True))
    if not department_ids:
        return True
    return user.department_id in department_ids


def get_visible_article_or_404(*, slug: str, user: User, include_archived: bool = False) -> Article:
    """get_object_or_404(Article, slug=...) plus the visibility check --
    a department-restricted article a user can't see 404s exactly like a
    slug that doesn't exist at all, rather than leaking its existence via
    a 403.
    """
    lookup = {"slug": slug} if include_archived else {"slug": slug, "is_archived": False}
    article = get_object_or_404(Article, **lookup)
    if not article_is_visible(article, user):
        raise Http404("Статья не найдена.")
    return article
