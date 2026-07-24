import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import services
from apps.assistant.exceptions import AssistantNotConfiguredError, AssistantRequestError
from apps.assistant.models import ArticleChunk

pytestmark = pytest.mark.django_db


def test_chunk_article_text_empty_for_no_content():
    user = UserFactory()
    article = article_services.create_article(title="Пустая", content_source="", created_by=user)

    assert services.chunk_article_text(article) == []


def test_chunk_article_text_prefixes_title_and_fits_in_one_chunk():
    user = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="Короткий текст статьи.", created_by=user
    )

    chunks = services.chunk_article_text(article)

    assert len(chunks) == 1
    assert chunks[0].startswith("Отпуска")
    assert "Короткий текст статьи." in chunks[0]


def test_chunk_article_text_splits_long_content_with_overlap():
    user = UserFactory()
    sentence = "Это предложение повторяется много раз в статье. "
    long_text = sentence * 100
    article = article_services.create_article(
        title="Длинная статья", content_source=long_text, created_by=user
    )

    chunks = services.chunk_article_text(article)

    assert len(chunks) > 1
    assert all(chunk.startswith("Длинная статья") for chunk in chunks)


def test_pack_unpack_embedding_roundtrip():
    vector = [0.1, -0.5, 3.25, 0.0]

    packed = services.pack_embedding(vector)
    unpacked = list(services.unpack_embedding(packed))

    assert unpacked == pytest.approx(vector, abs=1e-6)


def test_cosine_similarity_identical_vectors_is_one():
    assert services._cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert services._cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_sync_article_embeddings_noop_when_not_configured(settings):
    settings.OPENAI_API_KEY = ""
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст статьи", created_by=user
    )

    assert ArticleChunk.objects.filter(article=article).count() == 0


def test_sync_article_embeddings_raises_when_not_configured_and_asked_to(settings):
    settings.OPENAI_API_KEY = ""
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст статьи", created_by=user
    )

    with pytest.raises(AssistantNotConfiguredError):
        services.sync_article_embeddings(article, raise_on_error=True)


def test_sync_article_embeddings_creates_chunks(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0, 0.0]
    )
    user = UserFactory()

    article = article_services.create_article(
        title="Статья про отпуска", content_source="Текст про отпуска.", created_by=user
    )

    chunks = list(ArticleChunk.objects.filter(article=article))
    assert len(chunks) == 1
    assert chunks[0].embedding_model == settings.OPENAI_EMBEDDING_MODEL
    assert list(services.unpack_embedding(chunks[0].embedding)) == pytest.approx([1.0, 0.0, 0.0])


def test_sync_article_embeddings_recomputes_on_edit(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0, 0.0]
    )
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="исходный текст", created_by=user
    )
    first_chunk_id = ArticleChunk.objects.get(article=article).id

    article_services.update_article(
        article_id=article.pk,
        base_revision_id=article.current_revision_id,
        article_version=article.version,
        content_source="новый текст статьи",
        edited_by=user,
    )

    chunk = ArticleChunk.objects.get(article=article)
    assert chunk.id != first_chunk_id
    assert "новый текст статьи" in chunk.text


def test_sync_article_embeddings_removes_chunks_on_archive(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0, 0.0]
    )
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )
    assert ArticleChunk.objects.filter(article=article).exists()

    article_services.archive_article(article_id=article.pk, actor=user)

    assert not ArticleChunk.objects.filter(article=article).exists()


def test_sync_article_embeddings_keeps_existing_chunks_on_failure(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0, 0.0]
    )
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )
    original_chunk_id = ArticleChunk.objects.get(article=article).id

    def _boom(text):
        raise RuntimeError("OpenAI is down")

    monkeypatch.setattr("apps.assistant.openai_client.create_embedding", _boom)
    article.title = "Статья (переименована в памяти)"
    services.sync_article_embeddings(article)

    assert ArticleChunk.objects.get(article=article).id == original_chunk_id


def test_find_relevant_chunks_ranks_by_similarity(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory()

    vectors = {}

    def fake_embed(text):
        return vectors[text]

    monkeypatch.setattr("apps.assistant.openai_client.create_embedding", fake_embed)

    vectors["Отпуска\n\nКак оформить отпуск."] = [1.0, 0.0]
    article_a = article_services.create_article(
        title="Отпуска", content_source="Как оформить отпуск.", created_by=user
    )

    vectors["Бухгалтерия\n\nПорядок сдачи отчётности."] = [0.0, 1.0]
    article_services.create_article(
        title="Бухгалтерия", content_source="Порядок сдачи отчётности.", created_by=user
    )

    vectors["вопрос про отпуск"] = [1.0, 0.0]
    results = services.find_relevant_chunks("вопрос про отпуск")

    assert results[0].chunk.article == article_a
    assert results[0].score > results[-1].score


def test_find_relevant_chunks_excludes_archived_articles(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr("apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0])
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )
    article_services.archive_article(article_id=article.pk, actor=user)

    results = services.find_relevant_chunks("вопрос")

    assert results == []


def test_answer_question_rejects_empty_question():
    with pytest.raises(AssistantRequestError):
        services.answer_question("   ")


def test_answer_question_returns_canned_reply_when_nothing_relevant(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr("apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0])
    chat_called = []
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_chat_completion",
        lambda **kwargs: chat_called.append(kwargs) or "should not be called",
    )

    result = services.answer_question("вопрос без статей в базе")

    assert "не нашёл" in result.answer.lower()
    assert result.sources == []
    assert chat_called == []


def test_answer_question_builds_prompt_from_relevant_chunks_and_returns_sources(
    settings, monkeypatch
):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory()

    monkeypatch.setattr("apps.assistant.openai_client.create_embedding", lambda text: [1.0, 0.0])
    article = article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=user
    )

    captured = {}

    def fake_chat(*, system_prompt, user_prompt):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "Отпуск нужно оформить за две недели."

    monkeypatch.setattr("apps.assistant.openai_client.create_chat_completion", fake_chat)

    result = services.answer_question("Когда оформлять отпуск?")

    assert result.answer == "Отпуск нужно оформить за две недели."
    assert result.sources == [article]
    assert "Когда оформлять отпуск?" in captured["user_prompt"]
    assert "Отпуск оформляется за две недели." in captured["user_prompt"]
