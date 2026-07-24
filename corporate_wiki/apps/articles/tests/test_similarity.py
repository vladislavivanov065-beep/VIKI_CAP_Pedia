import pytest
from django.core.management import call_command

from apps.accounts.factories import UserFactory
from apps.articles import services
from apps.articles.models import ArticleSimilarity
from apps.articles.similarity import compute_all_similarities, find_similar_articles

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


def test_find_similar_articles_prefers_cache_over_live_computation():
    user = UserFactory()
    target = services.create_article(title="Карты", content_source="выпуск карт", created_by=user)
    close = services.create_article(
        title="Про карты подробно", content_source="выпуск карт клиентам", created_by=user
    )
    far = services.create_article(title="Кошки", content_source="мяу мяу мяу", created_by=user)

    # A deliberately "wrong" cache entry (far is not actually similar) --
    # if find_similar_articles reads this instead of recomputing live, it
    # proves the cache is actually consulted rather than always falling
    # back.
    ArticleSimilarity.objects.create(article=target, related_article=far, score=0.9, rank=1)

    results = find_similar_articles(target, limit=3)

    assert results == [far]
    assert close not in results


def test_compute_all_similarities_ranks_topically_close_articles_higher():
    user = UserFactory()
    a = services.create_article(
        title="Выпуск карт CardsPro",
        content_source="выпуск карт клиентам CardsPro",
        created_by=user,
    )
    b = services.create_article(
        title="Перевыпуск карт", content_source="перевыпуск карт клиентам CardsPro", created_by=user
    )
    c = services.create_article(title="Отпуска", content_source="правила отпусков", created_by=user)

    results = compute_all_similarities(limit=3)

    related_to_a = [related_id for related_id, _score in results[str(a.pk)]]
    assert str(b.pk) in related_to_a
    assert str(c.pk) not in related_to_a


def test_rebuild_similarity_cache_command_populates_cache_table():
    user = UserFactory()
    a = services.create_article(
        title="Выпуск карт CardsPro",
        content_source="выпуск карт клиентам CardsPro",
        created_by=user,
    )
    services.create_article(
        title="Перевыпуск карт", content_source="перевыпуск карт клиентам CardsPro", created_by=user
    )

    call_command("rebuild_similarity_cache")

    assert ArticleSimilarity.objects.filter(article=a).exists()


def test_rebuild_similarity_cache_command_is_idempotent():
    user = UserFactory()
    services.create_article(title="Карты", content_source="выпуск карт", created_by=user)
    services.create_article(
        title="Про карты подробно", content_source="выпуск карт клиентам", created_by=user
    )

    call_command("rebuild_similarity_cache")
    first_count = ArticleSimilarity.objects.count()
    call_command("rebuild_similarity_cache")
    second_count = ArticleSimilarity.objects.count()

    assert first_count == second_count
    assert first_count > 0
