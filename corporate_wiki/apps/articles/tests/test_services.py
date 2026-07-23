import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.exceptions import ArticleEditConflict, ArticleTitleConflict
from apps.articles.models import Article, ArticleRedirect, ArticleRevision

pytestmark = pytest.mark.django_db


def test_create_article_creates_first_revision_and_sets_it_current():
    user = UserFactory()

    article = services.create_article(
        title="Первая статья", content_source="Текст.", created_by=user
    )

    assert article.version == 1
    assert article.current_revision.revision_number == 1
    assert article.current_revision.content_source == "Текст."
    assert ArticleRevision.objects.filter(article=article).count() == 1


def test_create_article_generates_unicode_slug():
    user = UserFactory()
    article = services.create_article(title="Привет мир", content_source="х", created_by=user)
    assert article.slug == "привет-мир"
    assert Article.objects.filter(slug=article.slug).exists()


def test_create_article_rejects_case_insensitive_duplicate_title():
    user = UserFactory()
    services.create_article(title="Отпуск", content_source="a", created_by=user)

    with pytest.raises(ArticleTitleConflict):
        services.create_article(title="ОТПУСК", content_source="b", created_by=user)


def test_create_article_disambiguates_colliding_slugs():
    user = UserFactory()
    a = services.create_article(title="Тест", content_source="a", created_by=user)
    b = services.create_article(title="Тест!", content_source="b", created_by=user)
    assert a.slug != b.slug


def test_update_article_creates_new_revision_and_bumps_version():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)

    updated = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=user,
        edit_summary="Правка",
    )

    assert updated.version == 2
    assert updated.current_revision.revision_number == 2
    assert updated.current_revision.content_source == "v2"
    assert ArticleRevision.objects.filter(article=article).count() == 2


def test_update_article_raises_conflict_on_stale_version():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)
    stale_revision_id = article.current_revision_id
    stale_version = article.version

    services.update_article(
        article_id=article.pk,
        base_revision_id=stale_revision_id,
        article_version=stale_version,
        content_source="v2 от другого пользователя",
        edited_by=user,
    )

    with pytest.raises(ArticleEditConflict):
        services.update_article(
            article_id=article.pk,
            base_revision_id=stale_revision_id,
            article_version=stale_version,
            content_source="v2 конфликтующая версия",
            edited_by=user,
        )

    # The conflicting write must not have overwritten the saved revision.
    article.refresh_from_db()
    assert article.current_revision.content_source == "v2 от другого пользователя"
    assert ArticleRevision.objects.filter(article=article).count() == 2


def test_rename_article_updates_title_slug_and_creates_redirect():
    user = UserFactory()
    article = services.create_article(title="Старое имя", content_source="текст", created_by=user)
    old_slug = article.slug

    renamed = services.rename_article(
        article_id=article.pk,
        new_title="Новое имя",
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        edited_by=user,
    )

    assert renamed.title == "Новое имя"
    assert renamed.slug != old_slug
    assert ArticleRedirect.objects.filter(old_slug=old_slug, article=renamed).exists()
    assert renamed.current_revision.content_source == "текст"


def test_rename_article_rejects_conflicting_title():
    user = UserFactory()
    services.create_article(title="Занято", content_source="a", created_by=user)
    article = services.create_article(title="Свободно", content_source="b", created_by=user)

    with pytest.raises(ArticleTitleConflict):
        services.rename_article(
            article_id=article.pk,
            new_title="занято",
            base_revision_id=article.current_revision_id,
            article_version=article.version,
            edited_by=user,
        )


def test_archive_and_restore_article_round_trip():
    admin = UserFactory(is_staff=True, is_superuser=True)
    article = services.create_article(title="Статья", content_source="текст", created_by=admin)

    archived = services.archive_article(article_id=article.pk, actor=admin)
    assert archived.is_archived is True
    assert archived.archived_at is not None
    assert archived.archived_by == admin

    restored = services.restore_article(article_id=article.pk, actor=admin)
    assert restored.is_archived is False
    assert restored.archived_at is None
    assert restored.archived_by is None


def test_archived_article_history_and_revisions_are_preserved():
    admin = UserFactory(is_staff=True, is_superuser=True)
    article = services.create_article(title="Статья", content_source="v1", created_by=admin)
    services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=admin,
    )

    services.archive_article(article_id=article.pk, actor=admin)

    assert ArticleRevision.objects.filter(article=article).count() == 2


def test_restore_article_rejects_if_title_now_taken_by_another_active_article():
    admin = UserFactory(is_staff=True, is_superuser=True)
    article = services.create_article(title="Статья", content_source="v1", created_by=admin)
    services.archive_article(article_id=article.pk, actor=admin)

    services.create_article(title="Статья", content_source="другая статья", created_by=admin)

    with pytest.raises(ArticleTitleConflict):
        services.restore_article(article_id=article.pk, actor=admin)


def test_restore_revision_creates_new_version_and_preserves_history():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=user,
    )
    article = services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v3",
        edited_by=user,
    )
    assert article.version == 3

    restored = services.restore_revision(
        article_id=article.pk,
        revision_number=1,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        actor=user,
    )

    assert restored.version == 4
    assert restored.current_revision.content_source == "v1"
    assert restored.current_revision.restored_from.revision_number == 1
    assert ArticleRevision.objects.filter(article=article).count() == 4
    # Older revisions must still exist untouched.
    assert ArticleRevision.objects.get(article=article, revision_number=2).content_source == "v2"
