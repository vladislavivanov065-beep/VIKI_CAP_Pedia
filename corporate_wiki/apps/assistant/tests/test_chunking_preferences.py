import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import chunking_preferences
from apps.assistant.models import ArticleChunkingMethod, ArticleChunkingPreference

pytestmark = pytest.mark.django_db


def _article(**kwargs):
    admin = UserFactory()
    defaults = {"title": "Статья", "content_source": "текст", "created_by": admin}
    defaults.update(kwargs)
    return article_services.create_article(**defaults), admin


def test_prefers_chatgpt_is_false_without_any_recorded_preference():
    article, _admin = _article()

    assert chunking_preferences.prefers_chatgpt(article) is False


def test_prefers_chatgpt_is_true_after_an_explicit_chatgpt_choice():
    article, admin = _article()
    chunking_preferences.set_method(
        article=article, method=ArticleChunkingMethod.CHATGPT, actor=admin
    )

    assert chunking_preferences.prefers_chatgpt(article) is True


def test_prefers_chatgpt_is_false_after_an_explicit_local_choice():
    article, admin = _article()
    chunking_preferences.set_method(
        article=article, method=ArticleChunkingMethod.LOCAL, actor=admin
    )

    assert chunking_preferences.prefers_chatgpt(article) is False


def test_set_method_is_idempotent_and_updates_the_actor():
    article, admin = _article()
    other_admin = UserFactory()

    chunking_preferences.set_method(
        article=article, method=ArticleChunkingMethod.CHATGPT, actor=admin
    )
    chunking_preferences.set_method(
        article=article, method=ArticleChunkingMethod.LOCAL, actor=other_admin
    )

    assert ArticleChunkingPreference.objects.filter(article=article).count() == 1
    preference = ArticleChunkingPreference.objects.get(article=article)
    assert preference.method == ArticleChunkingMethod.LOCAL
    assert preference.updated_by == other_admin


def test_chatgpt_preferred_article_ids_returns_only_opted_in_articles():
    opted_in, admin = _article(title="Через ChatGPT")
    not_opted_in, _admin2 = _article(title="Локально")
    chunking_preferences.set_method(
        article=opted_in, method=ArticleChunkingMethod.CHATGPT, actor=admin
    )

    ids = chunking_preferences.chatgpt_preferred_article_ids([opted_in, not_opted_in])

    assert ids == {opted_in.id}


def test_undecided_articles_excludes_articles_with_a_recorded_preference():
    decided, admin = _article(title="Решено")
    undecided, _admin2 = _article(title="Не решено")
    chunking_preferences.set_method(
        article=decided, method=ArticleChunkingMethod.LOCAL, actor=admin
    )

    result = list(chunking_preferences.undecided_articles())

    assert result == [undecided]


def test_undecided_articles_excludes_archived_articles():
    admin = UserFactory()
    article = article_services.create_article(
        title="Архивная", content_source="текст", created_by=admin
    )
    article_services.archive_article(article_id=article.pk, actor=admin)

    assert list(chunking_preferences.undecided_articles()) == []
