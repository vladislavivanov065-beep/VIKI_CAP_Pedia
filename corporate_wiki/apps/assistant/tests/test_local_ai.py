import numpy as np
import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import local_ai
from apps.assistant.models import ArticleChunkEmbedding

pytestmark = pytest.mark.django_db


def _seed_one_chunk():
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=admin
    )
    return ArticleChunkEmbedding.objects.create(
        article=article,
        chunk_index=0,
        text="Отпуск оформляется за две недели.",
        embedding=np.array([1, 0, 0], dtype=np.float32).tobytes(),
    )


def test_answer_from_corpus_returns_none_when_nothing_trained():
    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None


def test_answer_from_corpus_returns_none_when_nothing_relevant_found(monkeypatch):
    _seed_one_chunk()
    monkeypatch.setattr("apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [])

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None


def test_answer_from_corpus_generates_answer_from_retrieved_chunks(monkeypatch):
    chunk = _seed_one_chunk()
    captured = {}

    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )

    def fake_generate(*, context, question):
        captured["context"] = context
        captured["question"] = question
        return "Отпуск нужно оформить за две недели."

    monkeypatch.setattr("apps.assistant.local_ai.local_models.generate_answer", fake_generate)

    answer = local_ai.answer_from_corpus(question="Когда оформлять отпуск?")

    assert answer == "Отпуск нужно оформить за две недели."
    assert "Отпуск оформляется за две недели." in captured["context"]
    assert "Отпуска" in captured["context"]
    assert captured["question"] == "Когда оформлять отпуск?"


def test_answer_from_corpus_returns_none_when_generation_fails(monkeypatch):
    chunk = _seed_one_chunk()
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )

    def _raise(*, context, question):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.local_ai.local_models.generate_answer", _raise)

    assert local_ai.answer_from_corpus(question="Когда оформлять отпуск?") is None
