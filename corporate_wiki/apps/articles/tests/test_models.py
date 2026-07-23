import pytest
from django.db import IntegrityError, transaction

from apps.accounts.factories import UserFactory
from apps.articles.models import Article

pytestmark = pytest.mark.django_db


def test_title_normalized_is_kept_in_sync_on_save():
    user = UserFactory()
    article = Article.objects.create(
        title="  Мой Заголовок  ", slug="moj-zagolovok", created_by=user
    )
    article.refresh_from_db()
    assert article.title_normalized == "мой заголовок".strip().lower()


def test_active_articles_cannot_share_a_case_insensitive_title():
    user = UserFactory()
    Article.objects.create(title="Отпуск", slug="otpusk", created_by=user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Article.objects.create(title="ОТПУСК", slug="otpusk-2", created_by=user)


def test_archived_article_does_not_block_reusing_its_title():
    user = UserFactory()
    first = Article.objects.create(title="Отпуск", slug="otpusk", created_by=user, is_archived=True)
    assert first.is_archived is True

    # Should not raise: the existing article with this title is archived.
    Article.objects.create(title="Отпуск", slug="otpusk-new", created_by=user)


def test_slug_is_unique():
    user = UserFactory()
    Article.objects.create(title="A", slug="dup-slug", created_by=user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Article.objects.create(title="B", slug="dup-slug", created_by=user)
