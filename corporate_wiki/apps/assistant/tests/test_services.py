import pytest

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import services
from apps.assistant.exceptions import AssistantRequestError

pytestmark = pytest.mark.django_db


def test_answer_question_rejects_empty_question(settings):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст статьи", created_by=user
    )

    with pytest.raises(AssistantRequestError):
        services.answer_question(article=article, question="   ")


def test_answer_question_returns_canned_reply_for_empty_article(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    chat_called = []
    monkeypatch.setattr(
        "apps.assistant.openai_client.create_chat_completion",
        lambda **kwargs: chat_called.append(kwargs) or "should not be called",
    )
    user = UserFactory()
    article = article_services.create_article(title="Пустая", content_source="", created_by=user)

    result = services.answer_question(article=article, question="Есть тут что-то?")

    assert "пока нет текста" in result.answer.lower()
    assert chat_called == []


def test_answer_question_sends_article_text_and_question_to_chat_model(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory()
    article = article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=user
    )

    captured = {}

    def fake_chat(*, system_prompt, user_prompt):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "Отпуск нужно оформить за две недели."

    monkeypatch.setattr("apps.assistant.openai_client.create_chat_completion", fake_chat)

    result = services.answer_question(article=article, question="Когда оформлять отпуск?")

    assert result.answer == "Отпуск нужно оформить за две недели."
    assert "Когда оформлять отпуск?" in captured["user_prompt"]
    assert "Отпуск оформляется за две недели." in captured["user_prompt"]
    assert "Отпуска" in captured["user_prompt"]


def test_answer_question_truncates_very_long_articles(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory()
    long_text = "Слово. " * 10000
    article = article_services.create_article(
        title="Длинная статья", content_source=long_text, created_by=user
    )

    captured = {}

    def fake_chat(*, system_prompt, user_prompt):
        captured["user_prompt"] = user_prompt
        return "ответ"

    monkeypatch.setattr("apps.assistant.openai_client.create_chat_completion", fake_chat)

    services.answer_question(article=article, question="Вопрос?")

    assert len(captured["user_prompt"]) < len(long_text)


def test_answer_question_propagates_not_configured_error(settings):
    settings.OPENAI_API_KEY = ""
    user = UserFactory()
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )

    from apps.assistant.exceptions import AssistantNotConfiguredError

    with pytest.raises(AssistantNotConfiguredError):
        services.answer_question(article=article, question="Вопрос?")
