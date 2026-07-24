import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.search import fts

pytestmark = pytest.mark.django_db


def test_creating_article_indexes_it_for_search():
    user = UserFactory()
    article_services.create_article(
        title="Отпускные правила", content_source="Порядок оформления отпуска.", created_by=user
    )

    hits = fts.search("отпускные")
    assert hits
    ids = {hit.article_id for hit in hits}
    assert str(article_services.Article.objects.get(title="Отпускные правила").pk) in ids


def test_search_is_cyrillic_case_insensitive():
    user = UserFactory()
    article_services.create_article(title="Командировки", content_source="x", created_by=user)

    assert fts.search("командировки")
    assert fts.search("КОМАНДИРОВКИ")
    assert fts.search("КоМаНдИрОвКи")


def test_prefix_query_matches_declined_forms():
    user = UserFactory()
    article_services.create_article(
        title="Правила", content_source="Порядок оформления отпуска сотрудника.", created_by=user
    )

    hits = fts.search("отпуск")
    assert hits


def test_editing_article_reindexes_content():
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="исходный текст", created_by=user
    )

    assert not fts.search("уникальноеслово")

    article_services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="теперь тут уникальноеслово",
        edited_by=user,
    )

    assert fts.search("уникальноеслово")


def test_archiving_article_keeps_it_in_index():
    user = UserFactory()
    article = article_services.create_article(
        title="Архивная статья", content_source="x", created_by=user
    )
    article_services.archive_article(article_id=article.pk, actor=user)

    hits = fts.search("архивная")
    assert str(article.pk) in {hit.article_id for hit in hits}


def test_multi_word_query_requires_all_tokens():
    user = UserFactory()
    both = article_services.create_article(
        title="Карты и деньги", content_source="выпуск карт клиентам", created_by=user
    )
    article_services.create_article(title="Только деньги", content_source="бюджет", created_by=user)

    hits = fts.search("карты деньги")
    ids = {hit.article_id for hit in hits}
    assert ids == {str(both.pk)}


def test_snippet_html_highlights_match():
    user = UserFactory()
    article = article_services.create_article(
        title="Статья",
        content_source="Порядок оформления ежегодного отпуска для сотрудников компании.",
        created_by=user,
    )

    snippet = fts.snippet_html(str(article.pk), "отпуска")
    assert snippet is not None
    assert "<mark>" in snippet and "</mark>" in snippet


def test_snippet_html_none_when_content_does_not_match():
    user = UserFactory()
    article = article_services.create_article(
        title="уникальныйтерм456", content_source="не относится", created_by=user
    )

    snippet = fts.snippet_html(str(article.pk), "уникальныйтерм456")
    assert snippet is None


def test_snippet_html_escapes_html_in_content():
    """snippet_html() must escape its own output regardless of what's in the
    index -- exercised directly against the FTS table (bypassing the
    markdown sanitizer, which would normally strip a literal <script> tag
    long before content reaches the index) to test that contract in
    isolation.
    """
    from django.db import connection

    user = UserFactory()
    article = article_services.create_article(title="Статья", content_source="x", created_by=user)
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {fts.FTS_TABLE} WHERE article_id = %s", [str(article.pk)])
        cursor.execute(
            f"INSERT INTO {fts.FTS_TABLE} (article_id, title, content) VALUES (%s, %s, %s)",
            [str(article.pk), article.title, "Текст про <script>alert(1)</script> и отпуск."],
        )

    snippet = fts.snippet_html(str(article.pk), "отпуск")
    assert snippet is not None
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet


def test_vocabulary_contains_indexed_terms():
    user = UserFactory()
    article_services.create_article(
        title="Статья", content_source="редкоеслово12345", created_by=user
    )

    assert "редкоеслово12345" in fts.vocabulary()


def test_rebuild_index_backfills_from_scratch():
    user = UserFactory()
    article_services.create_article(title="Первая", content_source="x", created_by=user)
    article_services.create_article(title="Вторая", content_source="y", created_by=user)

    count = fts.rebuild_index()
    assert count == 2
    assert fts.search("первая")
    assert fts.search("вторая")


def test_search_empty_query_returns_nothing():
    assert fts.search("") == []
    assert fts.search("   ") == []
