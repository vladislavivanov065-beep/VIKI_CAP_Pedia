"""Business logic for articles and their revision history.

Views call into this module instead of touching models directly (section
13). Every action is recorded both to the ``security`` logger (section
18) and as an immutable ``AuditLog`` row (Stage 9).
"""

from __future__ import annotations

import logging
import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.articles.exceptions import ArticleEditConflict, ArticleTitleConflict
from apps.articles.markdown_ext import render_article_content
from apps.articles.models import Article, ArticleRedirect, ArticleRevision
from apps.audit.services import record_event

security_logger = logging.getLogger("security")

# Fixed URL segments under /articles/ that a generated slug must never
# collide with (see apps/articles/urls.py).
RESERVED_SLUGS = {"create", "preview"}


def _log_event(
    action: str, *, actor: User | None, article: Article, user_agent: str = "", **metadata
) -> None:
    security_logger.info(
        "%s actor=%s article=%s metadata=%s",
        action,
        actor.email if actor else None,
        article.slug,
        metadata,
    )
    record_event(
        actor=actor,
        action=action,
        object_type="article",
        object_id=article.pk,
        metadata={"slug": article.slug, **{k: str(v) for k, v in metadata.items()}},
        user_agent=user_agent,
    )


def _generate_unique_slug(title: str, *, exclude_article_id: uuid.UUID | None = None) -> str:
    base = slugify(title, allow_unicode=True) or "article"
    candidate = base
    suffix = 2
    while True:
        taken = Article.objects.filter(slug=candidate)
        if exclude_article_id is not None:
            taken = taken.exclude(pk=exclude_article_id)
        if (
            candidate not in RESERVED_SLUGS
            and not taken.exists()
            and not ArticleRedirect.objects.filter(old_slug=candidate).exists()
        ):
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def _assert_title_available(title: str, *, exclude_article_id: uuid.UUID | None = None) -> None:
    normalized = title.strip().lower()
    conflict = Article.objects.filter(title_normalized=normalized, is_archived=False)
    if exclude_article_id is not None:
        conflict = conflict.exclude(pk=exclude_article_id)
    if conflict.exists():
        raise ArticleTitleConflict(f'Статья с заголовком "{title.strip()}" уже существует.')


def _check_optimistic_lock(article: Article, *, base_revision_id, article_version) -> None:
    current_revision_id = article.current_revision_id
    if article.version != article_version or str(current_revision_id or "") != str(
        base_revision_id or ""
    ):
        raise ArticleEditConflict(
            current_article=article, current_revision=article.current_revision
        )


def create_article(
    *,
    title: str,
    content_source: str,
    created_by: User,
    edit_summary: str = "",
    user_agent: str = "",
) -> Article:
    title = title.strip()
    _assert_title_available(title)

    with transaction.atomic():
        slug = _generate_unique_slug(title)
        article = Article.objects.create(
            title=title,
            slug=slug,
            created_by=created_by,
            version=1,
        )
        content_html, _toc_html = render_article_content(content_source)
        revision = ArticleRevision.objects.create(
            article=article,
            revision_number=1,
            title=title,
            content_source=content_source,
            content_html=content_html,
            edit_summary=edit_summary,
            edited_by=created_by,
        )
        article.current_revision = revision
        article.save(update_fields=["current_revision", "updated_at"])

    _log_event("article.created", actor=created_by, article=article, user_agent=user_agent)
    return article


def update_article(
    *,
    article_id: uuid.UUID,
    base_revision_id,
    article_version: int,
    content_source: str,
    edited_by: User,
    edit_summary: str = "",
    user_agent: str = "",
) -> Article:
    """Save a new revision of an article's content (not its title).

    Renaming goes through ``rename_article`` instead, so redirect
    bookkeeping always happens.
    """
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        _check_optimistic_lock(
            article, base_revision_id=base_revision_id, article_version=article_version
        )

        next_number = article.version + 1
        content_html, _toc_html = render_article_content(content_source)
        revision = ArticleRevision.objects.create(
            article=article,
            revision_number=next_number,
            title=article.title,
            content_source=content_source,
            content_html=content_html,
            edit_summary=edit_summary,
            edited_by=edited_by,
        )
        article.current_revision = revision
        article.version = next_number
        article.save(update_fields=["current_revision", "version", "updated_at"])

    _log_event(
        "article.edited",
        actor=edited_by,
        article=article,
        user_agent=user_agent,
        revision=revision.revision_number,
    )
    return article


def rename_article(
    *,
    article_id: uuid.UUID,
    new_title: str,
    base_revision_id,
    article_version: int,
    edited_by: User,
    edit_summary: str = "",
    user_agent: str = "",
) -> Article:
    new_title = new_title.strip()

    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        _check_optimistic_lock(
            article, base_revision_id=base_revision_id, article_version=article_version
        )
        _assert_title_available(new_title, exclude_article_id=article.pk)

        old_slug = article.slug
        new_slug = _generate_unique_slug(new_title, exclude_article_id=article.pk)

        next_number = article.version + 1
        current_content = (
            article.current_revision.content_source if article.current_revision else ""
        )
        current_html = article.current_revision.content_html if article.current_revision else ""
        revision = ArticleRevision.objects.create(
            article=article,
            revision_number=next_number,
            title=new_title,
            content_source=current_content,
            content_html=current_html,
            edit_summary=edit_summary
            or f'Статья переименована: "{article.title}" → "{new_title}".',
            edited_by=edited_by,
        )

        article.title = new_title
        article.slug = new_slug
        article.current_revision = revision
        article.version = next_number
        article.save(
            update_fields=[
                "title",
                "title_normalized",
                "slug",
                "current_revision",
                "version",
                "updated_at",
            ]
        )

        if old_slug != new_slug:
            ArticleRedirect.objects.create(old_slug=old_slug, article=article, created_by=edited_by)

    _log_event(
        "article.renamed",
        actor=edited_by,
        article=article,
        user_agent=user_agent,
        old_slug=old_slug,
    )
    return article


def archive_article(*, article_id: uuid.UUID, actor: User, user_agent: str = "") -> Article:
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        article.is_archived = True
        article.archived_at = timezone.now()
        article.archived_by = actor
        article.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])

    _log_event("article.archived", actor=actor, article=article, user_agent=user_agent)
    return article


def restore_article(*, article_id: uuid.UUID, actor: User, user_agent: str = "") -> Article:
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        _assert_title_available(article.title, exclude_article_id=article.pk)

        article.is_archived = False
        article.archived_at = None
        article.archived_by = None
        article.save(update_fields=["is_archived", "archived_at", "archived_by", "updated_at"])

    _log_event("article.restored", actor=actor, article=article, user_agent=user_agent)
    return article


def restore_revision(
    *,
    article_id: uuid.UUID,
    revision_number: int,
    base_revision_id,
    article_version: int,
    actor: User,
    user_agent: str = "",
) -> Article:
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article_id)
        _check_optimistic_lock(
            article, base_revision_id=base_revision_id, article_version=article_version
        )

        old_revision = article.revisions.get(revision_number=revision_number)

        next_number = article.version + 1
        new_revision = ArticleRevision.objects.create(
            article=article,
            revision_number=next_number,
            title=old_revision.title,
            content_source=old_revision.content_source,
            content_html=old_revision.content_html,
            edit_summary=f"Восстановлена версия №{revision_number}",
            edited_by=actor,
            restored_from=old_revision,
        )
        article.current_revision = new_revision
        article.version = next_number
        article.save(update_fields=["current_revision", "version", "updated_at"])

    _log_event(
        "revision.restored",
        actor=actor,
        article=article,
        user_agent=user_agent,
        restored_revision=revision_number,
    )
    return article
