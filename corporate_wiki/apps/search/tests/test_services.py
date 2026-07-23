import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.search.services import extract_snippet, search_articles, search_suggestions

pytestmark = pytest.mark.django_db


def test_exact_title_match_ranks_first():
    user = UserFactory()
    article_services.create_article(title="Отпуск и его виды", content_source="x", created_by=user)
    exact = article_services.create_article(title="Отпуск", content_source="x", created_by=user)

    results = search_articles("Отпуск")
    assert results[0].pk == exact.pk


def test_title_starts_with_ranks_before_title_contains():
    user = UserFactory()
    contains = article_services.create_article(
        title="Правила про отпуск", content_source="x", created_by=user
    )
    startswith = article_services.create_article(
        title="Отпуск и правила", content_source="x", created_by=user
    )

    results = search_articles("отпуск", limit=10)
    assert results.index(startswith) < results.index(contains)


def test_content_match_ranks_last_and_is_found():
    user = UserFactory()
    article = article_services.create_article(
        title="Совсем другое название",
        content_source="здесь упоминается уникальныйтерм123",
        created_by=user,
    )

    results = search_articles("уникальныйтерм123")
    assert article in results


def test_archived_articles_excluded_by_default():
    user = UserFactory()
    article = article_services.create_article(
        title="Архивоискатель", content_source="x", created_by=user
    )
    article_services.archive_article(article_id=article.pk, actor=user)

    assert search_articles("Архивоискатель") == []
    assert article in search_articles("Архивоискатель", include_archived=True)


def test_empty_query_returns_no_results():
    assert search_articles("") == []
    assert search_articles("   ") == []


def test_search_suggestions_requires_minimum_two_characters():
    user = UserFactory()
    article_services.create_article(title="Аб", content_source="x", created_by=user)
    assert search_suggestions("а") == []
    assert search_suggestions("аб") != []


def test_search_suggestions_only_matches_titles():
    user = UserFactory()
    article = article_services.create_article(
        title="Никак не связано", content_source="специальноеслово", created_by=user
    )
    assert search_suggestions("специальноеслово") == []
    assert article not in search_suggestions("специальноеслово")


def test_extract_snippet_centers_on_match():
    content = "а" * 100 + "ИСКОМОЕСЛОВО" + "б" * 100
    snippet = extract_snippet(content, "искомоеслово", context_chars=10)
    assert "ИСКОМОЕСЛОВО" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    assert len(snippet) < len(content)


def test_extract_snippet_falls_back_to_start_when_no_match():
    snippet = extract_snippet("некоторый текст без совпадения " * 5, "отсутствует")
    assert snippet


def test_extract_snippet_empty_content():
    assert extract_snippet("", "запрос") == ""


def test_search_is_case_insensitive_for_cyrillic_titles():
    """Regression guard: SQLite's LIKE/LOWER only fold ASCII case, so a
    naive title__istartswith/icontains against Cyrillic text silently
    fails for cross-case queries. Search must not regress to that.
    """
    user = UserFactory()
    article = article_services.create_article(
        title="Отпуск сотрудника", content_source="x", created_by=user
    )

    assert article in search_articles("отпуск")
    assert article in search_articles("ОТПУСК")
    assert article in search_suggestions("отпуск")


def test_search_content_match_is_case_insensitive_for_cyrillic():
    user = UserFactory()
    article = article_services.create_article(
        title="Другое", content_source="Текст содержит СЛОВОСПЕЦИАЛЬНОЕ здесь", created_by=user
    )
    assert article in search_articles("словоспециальное")
