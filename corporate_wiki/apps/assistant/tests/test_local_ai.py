import numpy as np
import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import local_ai
from apps.assistant.models import ArticleChunkEmbedding

pytestmark = pytest.mark.django_db


def _seed_one_chunk(*, text="Отпуск оформляется за две недели."):
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
    _seed_one_chunk()
    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [])

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None


def test_answer_from_corpus_extracts_the_matching_sentence_from_the_best_chunk(monkeypatch):
    chunk = _seed_one_chunk(
        text=(
            "Обед начинается в полдень. "
            "Отпуск оформляется за две недели. "
            "Столовая на первом этаже."
        )
    )
    captured = {}

    def fake_find_relevant_chunks(*, question, top_k):
        captured["question"] = question
        captured["top_k"] = top_k
        return [chunk]

    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", fake_find_relevant_chunks
    )

    answer = local_ai.answer_from_corpus(question="Когда оформлять отпуск?")

    assert answer == "Отпуск оформляется за две недели."
    assert captured["question"] == "Когда оформлять отпуск?"
    assert captured["top_k"] == 1


def test_answer_from_corpus_falls_back_to_the_whole_chunk_without_keyword_overlap(monkeypatch):
    # The retrieved chunk matched semantically (that's what embeddings are
    # for) but shares no exact keywords with the question -- still worth
    # returning as-is rather than discarding a genuinely relevant chunk.
    chunk = _seed_one_chunk(text="Единственное предложение фрагмента.")
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )

    answer = local_ai.answer_from_corpus(question="Совершенно другой вопрос")

    assert answer == "Единственное предложение фрагмента."


def test_answer_from_corpus_never_returns_more_than_one_sentence(monkeypatch):
    chunk = _seed_one_chunk(
        text=(
            "Отпуск оформляется за две недели. "
            "Отпуск можно продлить по заявлению. "
            "Обед начинается в полдень."
        )
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )

    answer = local_ai.answer_from_corpus(question="Как оформить отпуск?")

    assert answer in (
        "Отпуск оформляется за две недели.",
        "Отпуск можно продлить по заявлению.",
    )


def test_answer_from_corpus_returns_none_on_unexpected_error(monkeypatch):
    _seed_one_chunk()

    def _raise(**_kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", _raise)

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None
