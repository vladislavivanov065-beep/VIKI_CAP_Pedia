import numpy as np
import pytest

from apps.assistant import local_models


class _FakeEmbeddingModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        self.calls.append(list(texts))
        return np.zeros((len(texts), 3), dtype=np.float32)


def test_embed_texts_adds_e5_prefixes_for_e5_models(settings, monkeypatch):
    settings.LOCAL_AI_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
    fake = _FakeEmbeddingModel()
    monkeypatch.setattr(local_models, "_get_embedding_model", lambda: fake)

    local_models.embed_texts(["текст фрагмента"], is_query=False)
    local_models.embed_texts(["вопрос пользователя"], is_query=True)

    assert fake.calls[0] == ["passage: текст фрагмента"]
    assert fake.calls[1] == ["query: вопрос пользователя"]


def test_embed_texts_defaults_to_passage_prefix(settings, monkeypatch):
    settings.LOCAL_AI_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
    fake = _FakeEmbeddingModel()
    monkeypatch.setattr(local_models, "_get_embedding_model", lambda: fake)

    local_models.embed_texts(["текст"])

    assert fake.calls[0] == ["passage: текст"]


def test_embed_texts_does_not_prefix_non_e5_models(settings, monkeypatch):
    settings.LOCAL_AI_EMBEDDING_MODEL = "cointegrated/rubert-tiny2"
    fake = _FakeEmbeddingModel()
    monkeypatch.setattr(local_models, "_get_embedding_model", lambda: fake)

    local_models.embed_texts(["текст"], is_query=True)

    assert fake.calls[0] == ["текст"]


class _FakeCrossEncoder:
    def __init__(self):
        self.calls = []

    def predict(self, pairs, convert_to_numpy=True):
        self.calls.append(list(pairs))
        return np.array([0.9, 0.1], dtype=np.float32)


def test_score_pairs_pairs_the_question_with_each_candidate(monkeypatch):
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(local_models, "_get_cross_encoder_model", lambda: fake)

    scores = local_models.score_pairs(
        question="Когда оформлять отпуск?",
        candidates=["Отпуск оформляется за две недели.", "Обед начинается в полдень."],
    )

    assert fake.calls[0] == [
        ("Когда оформлять отпуск?", "Отпуск оформляется за две недели."),
        ("Когда оформлять отпуск?", "Обед начинается в полдень."),
    ]
    assert scores == pytest.approx([0.9, 0.1])


def test_score_pairs_returns_plain_python_floats(monkeypatch):
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(local_models, "_get_cross_encoder_model", lambda: fake)

    scores = local_models.score_pairs(question="Вопрос?", candidates=["А", "Б"])

    assert all(isinstance(score, float) for score in scores)
