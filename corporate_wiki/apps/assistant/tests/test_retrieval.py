import numpy as np
import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import retrieval
from apps.assistant.models import ArticleChunkEmbedding

pytestmark = pytest.mark.django_db


def _make_chunk(article, *, index, text, vector):
    return ArticleChunkEmbedding.objects.create(
        article=article,
        chunk_index=index,
        text=text,
        embedding=np.array(vector, dtype=np.float32).tobytes(),
    )


def test_find_relevant_chunks_ranks_a_single_articles_chunks_by_similarity(monkeypatch):
    admin = UserFactory()
    vacation = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=admin
    )
    _make_chunk(vacation, index=0, text="Отпуск оформляется за две недели.", vector=[1, 0, 0])
    _make_chunk(vacation, index=1, text="Обед начинается в полдень.", vector=[0, 1, 0])

    monkeypatch.setattr(
        "apps.assistant.retrieval.local_models.embed_texts",
        lambda texts, **kwargs: np.array([[1, 0, 0]], dtype=np.float32),
    )

    results = retrieval.find_relevant_chunks(question="Когда оформлять отпуск?", article=vacation)

    assert [chunk.text for chunk in results] == ["Отпуск оформляется за две недели."]


def test_find_relevant_chunks_never_returns_another_articles_chunks(monkeypatch):
    # The whole point of scoping by article: even a chunk that would rank
    # as a better semantic match must never surface here if it belongs to
    # a different article than the one the question was asked on.
    admin = UserFactory()
    vacation = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=admin
    )
    lunch = article_services.create_article(title="Обед", content_source="текст", created_by=admin)
    _make_chunk(vacation, index=0, text="Что-то не очень похожее.", vector=[0, 1, 0])
    _make_chunk(lunch, index=0, text="Обед начинается в полдень.", vector=[1, 0, 0])

    monkeypatch.setattr(
        "apps.assistant.retrieval.local_models.embed_texts",
        lambda texts, **kwargs: np.array([[1, 0, 0]], dtype=np.float32),
    )

    results = retrieval.find_relevant_chunks(question="Когда обед?", article=vacation)

    assert results == []


def test_find_relevant_chunks_excludes_low_similarity(monkeypatch):
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=admin
    )
    _make_chunk(article, index=0, text="Что-то про отпуск.", vector=[1, 0, 0])

    monkeypatch.setattr(
        "apps.assistant.retrieval.local_models.embed_texts",
        lambda texts, **kwargs: np.array([[0, 1, 0]], dtype=np.float32),
    )

    assert retrieval.find_relevant_chunks(question="Совсем другой вопрос", article=article) == []


def test_find_relevant_chunks_excludes_an_archived_article(monkeypatch):
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=admin
    )
    _make_chunk(article, index=0, text="Что-то про отпуск.", vector=[1, 0, 0])
    article_services.archive_article(article_id=article.pk, actor=admin)
    article.refresh_from_db()

    monkeypatch.setattr(
        "apps.assistant.retrieval.local_models.embed_texts",
        lambda texts, **kwargs: np.array([[1, 0, 0]], dtype=np.float32),
    )

    assert retrieval.find_relevant_chunks(question="Вопрос про отпуск", article=article) == []


def test_find_relevant_chunks_returns_empty_when_nothing_trained():
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=admin
    )

    assert retrieval.find_relevant_chunks(question="Вопрос?", article=article) == []


def test_find_relevant_chunks_embeds_the_question_as_a_query(monkeypatch):
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=admin
    )
    _make_chunk(article, index=0, text="Текст фрагмента.", vector=[1, 0, 0])

    captured = {}

    def fake_embed_texts(texts, **kwargs):
        captured["texts"] = texts
        captured["is_query"] = kwargs.get("is_query")
        return np.array([[1, 0, 0]], dtype=np.float32)

    monkeypatch.setattr("apps.assistant.retrieval.local_models.embed_texts", fake_embed_texts)

    retrieval.find_relevant_chunks(question="Вопрос?", article=article)

    assert captured["texts"] == ["Вопрос?"]
    assert captured["is_query"] is True
