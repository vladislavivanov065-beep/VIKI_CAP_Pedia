import uuid

import numpy as np
import pytest
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import training
from apps.assistant.models import ArticleChunkEmbedding, AssistantSettings

pytestmark = pytest.mark.django_db


def _fake_embed_texts(texts):
    """Distinct texts get orthogonal vectors (cosine similarity 0, below
    apps.assistant.chunking's merge thresholds), identical texts get
    identical vectors (similarity 1) -- deterministic, and keeps
    unrelated fake text from spuriously merging in these tests unless a
    test specifically supplies its own similarity-bearing fake (e.g. the
    address-block test below).
    """
    unique_texts = list(dict.fromkeys(texts))
    vectors = np.zeros((len(texts), max(len(unique_texts), 1)), dtype=np.float32)
    for row, text in enumerate(texts):
        vectors[row, unique_texts.index(text)] = 1.0
    return vectors


def _same_vector_fake_embed_texts(texts):
    return np.ones((len(texts), 3), dtype=np.float32)


def test_retrain_creates_chunk_embeddings_for_all_articles(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=admin
    )
    article_services.create_article(
        title="Обед", content_source="Обед начинается в полдень.", created_by=admin
    )

    training.retrain_local_model(actor=admin)

    solo = AssistantSettings.get_solo()
    assert solo.local_ai_is_training is False
    assert solo.local_ai_last_error == ""
    assert solo.local_ai_trained_at is not None
    assert solo.local_ai_trained_by == admin
    assert solo.local_ai_article_count == 2
    assert solo.local_ai_chunk_count == ArticleChunkEmbedding.objects.count()
    assert ArticleChunkEmbedding.objects.count() == 2


def test_retrain_counts_empty_articles_but_creates_no_chunk_for_them(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article_services.create_article(title="Пустая", content_source="", created_by=admin)

    training.retrain_local_model(actor=admin)

    solo = AssistantSettings.get_solo()
    assert solo.local_ai_article_count == 1
    assert solo.local_ai_chunk_count == 0
    assert ArticleChunkEmbedding.objects.count() == 0


def test_retrain_excludes_archived_articles(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="Текст статьи.", created_by=admin
    )
    article_services.archive_article(article_id=article.pk, actor=admin)

    training.retrain_local_model(actor=admin)

    solo = AssistantSettings.get_solo()
    assert solo.local_ai_article_count == 0
    assert ArticleChunkEmbedding.objects.count() == 0


def test_retrain_replaces_previous_chunks_rather_than_accumulating(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=admin
    )

    training.retrain_local_model(actor=admin)
    training.retrain_local_model(actor=admin)

    assert ArticleChunkEmbedding.objects.count() == 1


def test_retrain_raises_when_already_training():
    admin = UserFactory()
    solo = AssistantSettings.get_solo()
    solo.local_ai_is_training = True
    solo.save(update_fields=["local_ai_is_training"])

    with pytest.raises(training.LocalAiAlreadyTrainingError):
        training.retrain_local_model(actor=admin)


def test_retrain_records_error_without_raising(monkeypatch):
    admin = UserFactory()
    article_services.create_article(
        title="Статья", content_source="Текст статьи.", created_by=admin
    )

    def _raise(texts):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _raise)

    training.retrain_local_model(actor=admin)

    solo = AssistantSettings.get_solo()
    assert solo.local_ai_is_training is False
    assert "модель недоступна" in solo.local_ai_last_error
    assert solo.local_ai_trained_at is None


def test_retrain_logs_progress_for_each_article(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=admin
    )

    training.retrain_local_model(actor=admin)

    log = AssistantSettings.get_solo().local_ai_log
    assert "Начало обучения" in log
    assert "Отпуска" in log
    assert "Готово" in log


def test_retrain_logs_error(monkeypatch):
    admin = UserFactory()
    article_services.create_article(title="Статья", content_source="текст", created_by=admin)

    def _raise(texts):
        raise RuntimeError("модель недоступна")

    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _raise)

    training.retrain_local_model(actor=admin)

    log = AssistantSettings.get_solo().local_ai_log
    assert "Ошибка" in log
    assert "модель недоступна" in log


def test_begin_resets_log_before_a_new_run():
    solo = AssistantSettings.get_solo()
    solo.local_ai_log = "старый лог"
    solo.save(update_fields=["local_ai_log"])

    fresh = training._begin()

    assert fresh.local_ai_log == ""


class _ImmediateThread:
    """Runs the target synchronously instead of on a real thread, so
    background-training tests don't need real concurrency/timeouts."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def test_start_retrain_in_background_completes_via_patched_thread(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    monkeypatch.setattr("apps.assistant.training.threading.Thread", _ImmediateThread)
    admin = UserFactory()
    article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=admin
    )

    training.start_retrain_in_background(actor=admin)

    solo = AssistantSettings.get_solo()
    assert solo.local_ai_is_training is False
    assert solo.local_ai_trained_at is not None
    assert solo.local_ai_chunk_count == ArticleChunkEmbedding.objects.count()
    assert "Готово" in solo.local_ai_log


def test_start_retrain_in_background_raises_synchronously_when_already_training():
    admin = UserFactory()
    solo = AssistantSettings.get_solo()
    solo.local_ai_is_training = True
    solo.save(update_fields=["local_ai_is_training"])

    with pytest.raises(training.LocalAiAlreadyTrainingError):
        training.start_retrain_in_background(actor=admin)


def test_chunk_text_returns_one_row_per_block(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    text = (
        "Первое предложение тут.\n"
        "Что можно оплачивать: рекламу и хостинги, домены, нейросети.\n"
        "Третье предложение здесь."
    )

    chunks = training._chunk_text(text)

    assert chunks == [
        "Первое предложение тут.",
        "Что можно оплачивать: рекламу и хостинги, домены, нейросети.",
        "Третье предложение здесь.",
    ]


def test_chunk_text_merges_a_multi_line_address_into_one_block(monkeypatch):
    # A real embedding model would recognize these four lines as related
    # (all part of the same address); the fake stands in for that with
    # matching vectors, since neither line ends in punctuation but that
    # alone is no longer enough to merge them (see apps.assistant.chunking).
    monkeypatch.setattr(
        "apps.assistant.training.local_models.embed_texts", _same_vector_fake_embed_texts
    )
    text = "биллинг адрес\nулица такая-то\nгород такой то\nпос код такой то"

    chunks = training._chunk_text(text)

    assert chunks == ["биллинг адрес\nулица такая-то\nгород такой то\nпос код такой то"]


def test_chunk_text_does_not_merge_unrelated_lines_lacking_punctuation(monkeypatch):
    def fake_embed_texts(texts):
        vectors = {
            "заголовок раздела без точки": [1.0, 0.0],
            "совсем другой раздел тоже без точки": [0.0, 1.0],
        }
        return np.array([vectors[t] for t in texts], dtype=np.float32)

    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", fake_embed_texts)
    text = "заголовок раздела без точки\nсовсем другой раздел тоже без точки"

    chunks = training._chunk_text(text)

    assert chunks == ["заголовок раздела без точки", "совсем другой раздел тоже без точки"]


def test_chunk_text_keeps_a_multi_sentence_block_as_one_row():
    # Deliberately coarser than one row per grammatical sentence -- see
    # apps.assistant.training._chunk_text's docstring: this is what keeps
    # a paragraph introducing a list attached to that list.
    text = "Первое предложение. Второе предложение того же блока."

    chunks = training._chunk_text(text)

    assert chunks == ["Первое предложение. Второе предложение того же блока."]


def test_chunk_text_returns_empty_list_for_empty_text():
    assert training._chunk_text("") == []


def test_sync_article_embeddings_creates_a_row_per_block(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска",
        content_source="Отпуск оформляется за две недели.\n\nОбед начинается в полдень.",
        created_by=admin,
    )

    training.sync_article_embeddings(article)

    assert ArticleChunkEmbedding.objects.filter(article=article).count() == 2


def test_sync_article_embeddings_replaces_only_that_articles_rows(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="Текст статьи.", created_by=admin
    )
    other = article_services.create_article(
        title="Обед", content_source="Другой текст.", created_by=admin
    )
    training.sync_article_embeddings(article)
    training.sync_article_embeddings(other)

    training.sync_article_embeddings(article)

    assert ArticleChunkEmbedding.objects.filter(article=article).count() == 1
    assert ArticleChunkEmbedding.objects.filter(article=other).count() == 1


def test_sync_article_embeddings_removes_rows_for_an_archived_article(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="Текст статьи.", created_by=admin
    )
    training.sync_article_embeddings(article)
    assert ArticleChunkEmbedding.objects.filter(article=article).count() == 1

    article_services.archive_article(article_id=article.pk, actor=admin)
    article.refresh_from_db()
    training.sync_article_embeddings(article)

    assert ArticleChunkEmbedding.objects.filter(article=article).count() == 0


def test_sync_article_embeddings_leaves_no_rows_for_empty_text(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.local_models.embed_texts", _fake_embed_texts)
    admin = UserFactory()
    article = article_services.create_article(title="Пустая", content_source="", created_by=admin)

    training.sync_article_embeddings(article)

    assert ArticleChunkEmbedding.objects.filter(article=article).count() == 0


def test_start_sync_article_embeddings_in_background_is_a_noop_before_first_retrain(
    monkeypatch,
):
    monkeypatch.setattr("apps.assistant.training.threading.Thread", _ImmediateThread)
    called = []
    monkeypatch.setattr(
        "apps.assistant.training._run_sync_article_embeddings_in_background",
        lambda article_id: called.append(article_id),
    )

    training.start_sync_article_embeddings_in_background(uuid.uuid4())

    assert called == []


def test_start_sync_article_embeddings_in_background_runs_after_first_retrain(monkeypatch):
    monkeypatch.setattr("apps.assistant.training.threading.Thread", _ImmediateThread)
    solo = AssistantSettings.get_solo()
    solo.local_ai_trained_at = timezone.now()
    solo.save(update_fields=["local_ai_trained_at"])
    called = []
    monkeypatch.setattr(
        "apps.assistant.training._run_sync_article_embeddings_in_background",
        lambda article_id: called.append(article_id),
    )
    article_id = uuid.uuid4()

    training.start_sync_article_embeddings_in_background(article_id)

    assert called == [article_id]
