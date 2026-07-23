import pytest

from apps.accounts.factories import UserFactory
from apps.articles import selectors, services
from apps.articles.models import Article

pytestmark = pytest.mark.django_db


def test_get_article_by_slug_excludes_archived_by_default():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="a", created_by=user)
    services.archive_article(article_id=article.pk, actor=user)

    with pytest.raises(Article.DoesNotExist):
        selectors.get_article_by_slug(article.slug)

    assert selectors.get_article_by_slug(article.slug, include_archived=True).pk == article.pk


def test_get_article_history_orders_newest_first():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)
    services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="v2",
        edited_by=user,
    )

    history = list(selectors.get_article_history(article))
    assert [r.revision_number for r in history] == [2, 1]


def test_get_revision_returns_specific_revision_number():
    user = UserFactory()
    article = services.create_article(title="Статья", content_source="v1", created_by=user)
    revision = selectors.get_revision(article, 1)
    assert revision.content_source == "v1"


def test_get_recent_articles_excludes_archived_and_orders_by_updated():
    user = UserFactory()
    old = services.create_article(title="Старая", content_source="a", created_by=user)
    new = services.create_article(title="Новая", content_source="b", created_by=user)
    archived = services.create_article(title="Архивная", content_source="c", created_by=user)
    services.archive_article(article_id=archived.pk, actor=user)

    recent = list(selectors.get_recent_articles(limit=10))
    assert archived not in recent
    assert recent.index(new) < recent.index(old)


def test_get_user_contributions_returns_only_that_users_revisions():
    alice = UserFactory()
    bob = UserFactory()
    services.create_article(title="Статья Алисы", content_source="a", created_by=alice)
    services.create_article(title="Статья Боба", content_source="b", created_by=bob)

    contributions = selectors.get_user_contributions(alice)
    assert contributions.count() == 1
    assert contributions.first().edited_by == alice
