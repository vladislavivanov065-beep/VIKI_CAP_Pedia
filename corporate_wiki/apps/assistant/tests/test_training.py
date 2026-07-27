import numpy as np
import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import training
from apps.assistant.models import ArticleChunkEmbedding, AssistantSettings

pytestmark = pytest.mark.django_db


def _fake_embed_texts(texts):
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


def test_chunk_text_never_splits_a_sentence_across_chunks():
    text = (
        "Первое предложение тут. "
        "Что можно оплачивать: рекламу и хостинги, домены, нейросети. "
        "Третье предложение здесь."
    )

    chunks = training._chunk_text(text, chunk_chars=40)

    for sentence in [
        "Первое предложение тут.",
        "Что можно оплачивать: рекламу и хостинги, домены, нейросети.",
        "Третье предложение здесь.",
    ]:
        assert any(sentence in chunk for chunk in chunks)


def test_chunk_text_keeps_a_single_long_sentence_as_one_chunk():
    long_sentence = "Слово " * 30 + "тут."

    chunks = training._chunk_text(long_sentence, chunk_chars=20)

    assert len(chunks) == 1
    assert chunks[0] == long_sentence


def test_chunk_text_returns_empty_list_for_empty_text():
    assert training._chunk_text("") == []
