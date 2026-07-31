import numpy as np

from apps.assistant import chunking


def _orthogonal_fake_embed_texts(texts):
    unique_texts = list(dict.fromkeys(texts))
    vectors = np.zeros((len(texts), max(len(unique_texts), 1)), dtype=np.float32)
    for row, text in enumerate(texts):
        vectors[row, unique_texts.index(text)] = 1.0
    return vectors


def test_group_into_chunks_returns_empty_list_for_empty_text():
    assert chunking.group_into_chunks("") == []


def test_group_into_chunks_returns_the_single_line_unchanged():
    assert chunking.group_into_chunks("Одна строка.") == ["Одна строка."]


def test_group_into_chunks_merges_lines_without_terminal_punctuation(monkeypatch):
    monkeypatch.setattr(
        "apps.assistant.chunking.local_models.embed_texts", _orthogonal_fake_embed_texts
    )
    text = "биллинг адрес\nулица такая-то\nгород такой то\nпос код такой то"

    assert chunking.group_into_chunks(text) == [
        "биллинг адрес улица такая-то город такой то пос код такой то"
    ]


def test_group_into_chunks_keeps_punctuated_unrelated_lines_separate(monkeypatch):
    monkeypatch.setattr(
        "apps.assistant.chunking.local_models.embed_texts", _orthogonal_fake_embed_texts
    )
    text = "Первое предложение.\nВторое, никак не связанное предложение."

    assert chunking.group_into_chunks(text) == [
        "Первое предложение.",
        "Второе, никак не связанное предложение.",
    ]


def test_group_into_chunks_merges_semantically_similar_lines_even_with_punctuation(monkeypatch):
    # Both lines end with "." (no punctuation-based reason to merge), but
    # a high embedding similarity between them is enough on its own.
    def fake_embed_texts(texts):
        vectors = {
            "Заголовок раздела про отпуска.": [1.0, 0.0],
            "Он тоже про отпуска и связан с этим разделом.": [0.95, 0.05],
        }
        return np.array([vectors[t] for t in texts], dtype=np.float32)

    monkeypatch.setattr("apps.assistant.chunking.local_models.embed_texts", fake_embed_texts)
    text = "Заголовок раздела про отпуска.\nОн тоже про отпуска и связан с этим разделом."

    assert chunking.group_into_chunks(text) == [
        "Заголовок раздела про отпуска. Он тоже про отпуска и связан с этим разделом."
    ]


def test_group_into_chunks_caps_a_long_run_of_unpunctuated_lines(monkeypatch):
    monkeypatch.setattr(
        "apps.assistant.chunking.local_models.embed_texts", _orthogonal_fake_embed_texts
    )
    lines = [f"пункт {i}" for i in range(chunking._MAX_GROUP_LINES + 5)]
    text = "\n".join(lines)

    chunks = chunking.group_into_chunks(text)

    assert len(chunks[0].split(" ")) <= chunking._MAX_GROUP_LINES * 2
    assert len(chunks) > 1
