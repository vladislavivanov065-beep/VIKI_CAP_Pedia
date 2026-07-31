import numpy as np
import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import local_ai
from apps.assistant.models import ArticleChunkEmbedding

pytestmark = pytest.mark.django_db


def _seed_one_sentence(*, text="Отпуск оформляется за две недели."):
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=admin
    )
    return ArticleChunkEmbedding.objects.create(
        article=article,
        chunk_index=0,
        text=text,
        embedding=np.array([1, 0, 0], dtype=np.float32).tobytes(),
    )


def test_answer_from_article_returns_none_when_nothing_trained():
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=admin
    )

    assert local_ai.answer_from_article(question="Когда оформлять отпуск?", article=article) is None


def test_answer_from_article_returns_none_when_nothing_relevant_found(monkeypatch):
    chunk = _seed_one_sentence()
    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [])

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=chunk.article)

    assert answer is None


def test_answer_from_article_requests_a_pool_of_candidates_for_this_article(monkeypatch):
    chunk = _seed_one_sentence()
    captured = {}

    def fake_find_relevant_chunks(*, question, article, top_k):
        captured["question"] = question
        captured["article"] = article
        captured["top_k"] = top_k
        return [chunk]

    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", fake_find_relevant_chunks
    )

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=chunk.article)

    assert answer == "Отпуск оформляется за две недели."
    assert captured["question"] == "Когда оформлять отпуск?"
    assert captured["article"] == chunk.article
    assert captured["top_k"] == local_ai._CANDIDATE_POOL_SIZE


def test_answer_from_article_reranks_candidates_by_keyword_overlap(monkeypatch):
    # The embedding search ranks these two sentences in this order, but the
    # second one actually shares the question's words -- reranking by
    # lexical overlap across the whole candidate pool should surface it
    # instead of blindly trusting the embedding's top pick.
    top_embedding_match = _seed_one_sentence(text="Обед начинается в полдень.")
    lexically_relevant = ArticleChunkEmbedding.objects.create(
        article=top_embedding_match.article,
        chunk_index=1,
        text="Отпуск оформляется за две недели.",
        embedding=np.array([0, 1, 0], dtype=np.float32).tobytes(),
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks",
        lambda **_: [top_embedding_match, lexically_relevant],
    )

    answer = local_ai.answer_from_article(
        question="Когда оформлять отпуск?", article=top_embedding_match.article
    )

    assert answer == "Отпуск оформляется за две недели."


def test_answer_from_article_falls_back_to_the_top_embedding_match_without_keyword_overlap(
    monkeypatch,
):
    # None of the candidates share an exact keyword with the question --
    # still worth returning the top embedding match rather than discarding
    # a genuinely relevant (semantically, if not lexically) result.
    chunk = _seed_one_sentence(text="Единственное предложение фрагмента.")
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )

    answer = local_ai.answer_from_article(
        question="Совершенно другой вопрос", article=chunk.article
    )

    assert answer == "Единственное предложение фрагмента."


def test_answer_from_article_returns_none_on_unexpected_error(monkeypatch):
    chunk = _seed_one_sentence()

    def _raise(**_kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", _raise)

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=chunk.article)

    assert answer is None


def test_answer_from_article_never_searches_a_different_article(monkeypatch):
    # A local AI index exists (for a *different* article), but the article
    # this question was asked about has no chunks of its own -- must not
    # fall through to searching anything else.
    _seed_one_sentence()
    admin = UserFactory()
    other_article = article_services.create_article(
        title="Другая статья", content_source="текст", created_by=admin
    )

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=other_article)

    assert answer is None
