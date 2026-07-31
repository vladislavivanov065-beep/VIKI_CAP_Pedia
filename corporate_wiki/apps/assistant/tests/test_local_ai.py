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


def _fake_score_pairs(scores):
    def score_pairs(*, question, candidates):
        return scores[: len(candidates)]

    return score_pairs


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
    monkeypatch.setattr(
        "apps.assistant.local_ai.local_models.score_pairs", _fake_score_pairs([0.9])
    )

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=chunk.article)

    assert answer.text == "Отпуск оформляется за две недели."
    assert captured["question"] == "Когда оформлять отпуск?"
    assert captured["article"] == chunk.article
    assert captured["top_k"] == local_ai._CANDIDATE_POOL_SIZE


def test_answer_from_article_picks_the_highest_cross_encoder_score(monkeypatch):
    low_score_first = _seed_one_sentence(text="Обед начинается в полдень.")
    high_score_second = ArticleChunkEmbedding.objects.create(
        article=low_score_first.article,
        chunk_index=1,
        text="Отпуск оформляется за две недели.",
        embedding=np.array([0, 1, 0], dtype=np.float32).tobytes(),
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks",
        lambda **_: [low_score_first, high_score_second],
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.local_models.score_pairs", _fake_score_pairs([0.2, 0.9])
    )

    answer = local_ai.answer_from_article(
        question="Когда оформлять отпуск?", article=low_score_first.article
    )

    assert answer.text == "Отпуск оформляется за две недели."
    assert answer.alternatives == []


def test_answer_from_article_surfaces_alternatives_when_confidence_is_low(monkeypatch):
    best = _seed_one_sentence(text="Первый кандидат.")
    second = ArticleChunkEmbedding.objects.create(
        article=best.article, chunk_index=1, text="Второй кандидат.", embedding=b"\x00" * 12
    )
    third = ArticleChunkEmbedding.objects.create(
        article=best.article, chunk_index=2, text="Третий кандидат.", embedding=b"\x00" * 12
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks",
        lambda **_: [best, second, third],
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.local_models.score_pairs",
        _fake_score_pairs([0.4, 0.3, 0.2]),
    )

    answer = local_ai.answer_from_article(question="Вопрос?", article=best.article)

    assert answer.text == "Первый кандидат."
    assert answer.alternatives == ["Второй кандидат.", "Третий кандидат."]


def test_answer_from_article_caps_alternatives_at_max_alternatives(monkeypatch):
    best = _seed_one_sentence(text="Кандидат 0.")
    others = [
        ArticleChunkEmbedding.objects.create(
            article=best.article, chunk_index=i, text=f"Кандидат {i}.", embedding=b"\x00" * 12
        )
        for i in range(1, 5)
    ]
    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks",
        lambda **_: [best, *others],
    )
    monkeypatch.setattr(
        "apps.assistant.local_ai.local_models.score_pairs",
        _fake_score_pairs([0.4, 0.35, 0.3, 0.25, 0.2]),
    )

    answer = local_ai.answer_from_article(question="Вопрос?", article=best.article)

    assert len(answer.alternatives) == local_ai._MAX_ALTERNATIVES


def test_answer_from_article_falls_back_to_keyword_overlap_when_cross_encoder_fails(monkeypatch):
    chunk = _seed_one_sentence(text="Отпуск оформляется за две недели.")

    def _raise(**_kwargs):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr(
        "apps.assistant.local_ai.retrieval.find_relevant_chunks", lambda **_: [chunk]
    )
    monkeypatch.setattr("apps.assistant.local_ai.local_models.score_pairs", _raise)

    answer = local_ai.answer_from_article(question="Когда оформлять отпуск?", article=chunk.article)

    assert answer.text == "Отпуск оформляется за две недели."
    assert answer.alternatives == []


def test_answer_from_article_returns_none_on_unexpected_retrieval_error(monkeypatch):
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
