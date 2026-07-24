import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.similarity import find_similar_articles

pytestmark = pytest.mark.django_db


def test_finds_the_most_topically_similar_articles_first():
    user = UserFactory()
    target = services.create_article(
        title="Выпуск карт CardsPro",
        content_source=(
            "CardsPro — сервис для выпуска банковских карт клиентам. "
            "Поддерживает выпуск карт, перевыпуск карт и блокировку карт."
        ),
        created_by=user,
    )
    close = services.create_article(
        title="Перевыпуск карт в CardsPro",
        content_source="Как оформить перевыпуск карты клиенту через CardsPro.",
        created_by=user,
    )
    unrelated = services.create_article(
        title="Отпускные правила",
        content_source="Порядок оформления отпуска и расчёта отпускных выплат сотрудникам.",
        created_by=user,
    )

    results = find_similar_articles(target, limit=3)

    assert close in results
    assert results.index(close) < (results.index(unrelated) if unrelated in results else 999)


def test_excludes_self_and_archived_articles():
    user = UserFactory()
    target = services.create_article(
        title="Статья", content_source="уникальный текст про кошек", created_by=user
    )
    archived = services.create_article(
        title="Архивная про кошек", content_source="уникальный текст про кошек", created_by=user
    )
    services.archive_article(article_id=archived.pk, actor=user)

    results = find_similar_articles(target, limit=3)

    assert target not in results
    assert archived not in results


def test_returns_empty_list_when_nothing_shares_meaningful_terms():
    user = UserFactory()
    target = services.create_article(title="Кошки", content_source="мяу мяу мяу", created_by=user)
    services.create_article(
        title="Бухгалтерия", content_source="налоговая отчётность за квартал", created_by=user
    )

    results = find_similar_articles(target, limit=3)

    assert results == []


def test_returns_empty_list_when_no_other_articles_exist():
    user = UserFactory()
    target = services.create_article(
        title="Единственная статья", content_source="текст", created_by=user
    )

    assert find_similar_articles(target, limit=3) == []


def test_respects_limit():
    user = UserFactory()
    target = services.create_article(
        title="Карты CardsPro", content_source="выпуск карт CardsPro", created_by=user
    )
    for i in range(5):
        services.create_article(
            title=f"Карты статья {i}",
            content_source="выпуск карт CardsPro клиентам",
            created_by=user,
        )

    results = find_similar_articles(target, limit=3)

    assert len(results) <= 3
