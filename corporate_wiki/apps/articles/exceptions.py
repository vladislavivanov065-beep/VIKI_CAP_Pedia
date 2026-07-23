from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.articles.models import Article, ArticleRevision


class ArticleTitleConflict(Exception):
    """A different, non-archived article already has this title (section 4.1)."""


class ArticleEditConflict(Exception):
    """The article was changed by someone else since the editor opened it.

    Carries the current DB state so the caller (a future view, per section
    4.5) can show "your version" vs. "the saved version" and offer a diff,
    instead of silently overwriting anything.
    """

    def __init__(self, *, current_article: Article, current_revision: ArticleRevision | None):
        self.current_article = current_article
        self.current_revision = current_revision
        super().__init__("Статья была изменена другим пользователем.")
