import numpy as np

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
