"""Reads and writes apps.assistant.models.ArticleChunkingPreference -- kept
separate from apps.assistant.training so training doesn't need to know
anything about the model beyond "give me a yes/no per article", and so
apps.assistant.views has one small place to call into for the "Локальный
ИИ" admin page's undecided-articles list.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import QuerySet

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant.models import ArticleChunkingMethod, ArticleChunkingPreference


def prefers_chatgpt(article: Article) -> bool:
    """Single-article lookup -- used by the incremental per-save resync
    (apps.assistant.training.sync_article_embeddings), where one extra
    query for one article is negligible.
    """
    return ArticleChunkingPreference.objects.filter(
        article=article, method=ArticleChunkingMethod.CHATGPT
    ).exists()


def chatgpt_preferred_article_ids(articles: Iterable[Article]) -> set:
    """Bulk version of prefers_chatgpt for a full retrain's article list --
    one query for every article instead of one query per article.
    """
    return set(
        ArticleChunkingPreference.objects.filter(
            article__in=articles, method=ArticleChunkingMethod.CHATGPT
        ).values_list("article_id", flat=True)
    )


def undecided_articles() -> QuerySet[Article]:
    """Non-archived articles with no recorded chunking preference yet --
    shown on the "Локальный ИИ" admin page so an administrator can opt
    individual articles into ChatGPT-assisted chunking; everything else
    stays local by default without any action needed.
    """
    return Article.objects.filter(is_archived=False, chunking_preference__isnull=True).order_by(
        "-updated_at"
    )


def set_method(*, article: Article, method: str, actor: User) -> ArticleChunkingPreference:
    preference, _created = ArticleChunkingPreference.objects.update_or_create(
        article=article, defaults={"method": method, "updated_by": actor}
    )
    return preference
