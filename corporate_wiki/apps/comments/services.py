"""Creating comments and grouping them into threads for display.

Deliberately only one level of replies: apps.comments.models.Comment has
a self-FK, but nothing stops a caller from passing a reply as the
`parent` of another comment -- create_comment is what actually enforces
the rule, by attaching to the original top-level comment instead of
nesting further. A UI that only ever offers "Ответить" on top-level
comments never triggers this, but the guarantee holds even against a
crafted request.
"""

from __future__ import annotations

import dataclasses

from apps.accounts.models import User
from apps.articles.models import Article
from apps.comments.models import Comment


def create_comment(
    *, article: Article, author: User, text: str, parent: Comment | None = None
) -> Comment:
    if parent is not None and parent.parent_id is not None:
        parent = parent.parent
    return Comment.objects.create(article=article, author=author, text=text, parent=parent)


@dataclasses.dataclass
class CommentThread:
    comment: Comment
    replies: list[Comment]


def get_comment_threads(article: Article) -> list[CommentThread]:
    """One query for every comment on the article, then grouped in Python
    -- top-level comments in the order they were posted, each with its
    own replies (also posted-order) attached, so a reply always renders
    directly after the comment it answers.
    """
    comments = list(
        Comment.objects.filter(article=article).select_related("author").order_by("created_at")
    )

    replies_by_parent_id: dict = {}
    top_level: list[Comment] = []
    for comment in comments:
        if comment.parent_id is None:
            top_level.append(comment)
        else:
            replies_by_parent_id.setdefault(comment.parent_id, []).append(comment)

    return [
        CommentThread(comment=comment, replies=replies_by_parent_id.get(comment.id, []))
        for comment in top_level
    ]
