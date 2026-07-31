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


def test_answer_from_corpus_returns_none_when_nothing_trained():
    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None


def test_answer_from_corpus_returns_none_when_nothing_relevant_found(monkeypatch):
    _seed_one_sentence()
    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [])

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None


def test_answer_from_corpus_requests_a_pool_of_candidates(monkeypatch):
    sentence = _seed_one_sentence()
    captured = {}

    def fake_find_relevant_chunks(*, question, top_k):
        captured["question"] = question
        captured["top_k"] = top_k
        return [sentence]

    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", fake_find_relevant_chunks
    )

    answer = local_ai.answer_from_corpus(question="Когда оформлять отпуск?")

    assert answer == "Отпуск оформляется за две недели."
    assert captured["question"] == "Когда оформлять отпуск?"
    assert captured["top_k"] == local_ai._CANDIDATE_POOL_SIZE


def test_answer_from_corpus_reranks_candidates_by_keyword_overlap(monkeypatch):
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

    answer = local_ai.answer_from_corpus(question="Когда оформлять отпуск?")

    assert answer == "Отпуск оформляется за две недели."


def test_answer_from_corpus_falls_back_to_the_top_embedding_match_without_keyword_overlap(
    monkeypatch,
):
    # None of the candidates share an exact keyword with the question --
    # still worth returning the top embedding match rather than discarding
    # a genuinely relevant (semantically, if not lexically) result.
    sentence = _seed_one_sentence(text="Единственное предложение фрагмента.")
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [sentence]
    )

    answer = local_ai.answer_from_corpus(question="Совершенно другой вопрос")

    assert answer == "Единственное предложение фрагмента."


def test_answer_from_corpus_returns_none_on_unexpected_error(monkeypatch):
    _seed_one_sentence()

    def _raise(**_kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", _raise)

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None
