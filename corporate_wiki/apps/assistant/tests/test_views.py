import json

import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services
from apps.assistant import services
from apps.assistant.models import AssistantSettings
from apps.assistant.services import AnswerResult

pytestmark = pytest.mark.django_db


def _ask(client, **payload):
    return client.post(
        reverse("assistant:ask"), data=json.dumps(payload), content_type="application/json"
    )


def test_ask_requires_authentication(client):
    response = _ask(client, question="вопрос", article_slug="test")
    assert response.status_code == 302


def test_ask_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("assistant:ask"))
    assert response.status_code == 405


def test_ask_rejects_empty_question(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = _ask(client, question="  ", article_slug="test")
    assert response.status_code == 400
    assert "error" in response.json()


def test_ask_rejects_missing_article_slug(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = _ask(client, question="вопрос")
    assert response.status_code == 400
    assert "error" in response.json()


def test_ask_rejects_malformed_json(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(
        reverse("assistant:ask"), data="not json", content_type="application/json"
    )
    assert response.status_code == 400


def test_ask_404s_for_unknown_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = _ask(client, question="вопрос", article_slug="no-such-article")
    assert response.status_code == 404


def test_ask_404s_for_archived_article(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )
    article_services.archive_article(article_id=article.pk, actor=user)

    response = _ask(client, question="вопрос", article_slug=article.slug)
    assert response.status_code == 404


def test_ask_returns_answer(client, monkeypatch):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Отпуска", content_source="текст", created_by=user
    )

    monkeypatch.setattr(
        "apps.assistant.views.services.answer_question",
        lambda article, question: AnswerResult(answer="Ответ на вопрос."),
    )

    response = _ask(
        client, question="Как оформить отпуск?", article_slug=article.slug, use_chatgpt=True
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "Ответ на вопрос.", "source": "chatgpt"}


def test_ask_defaults_to_local_search_without_use_chatgpt_flag(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=user
    )

    response = _ask(client, question="Когда оформлять отпуск?", article_slug=article.slug)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "local"
    assert "Отпуск оформляется за две недели." in body["answer"]


def test_ask_local_search_ignores_global_disable(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Отпуска", content_source="Отпуск оформляется за две недели.", created_by=user
    )
    services.set_assistant_enabled(enabled=False, actor=user)

    response = _ask(
        client,
        question="Когда оформлять отпуск?",
        article_slug=article.slug,
        use_chatgpt=False,
    )

    assert response.status_code == 200
    assert response.json()["source"] == "local"


def test_ask_reports_not_configured_as_service_unavailable(client, monkeypatch):
    from apps.assistant.exceptions import AssistantNotConfiguredError

    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )

    def _raise(article, question):
        raise AssistantNotConfiguredError("не настроено")

    monkeypatch.setattr("apps.assistant.views.services.answer_question", _raise)

    response = _ask(client, question="вопрос", article_slug=article.slug, use_chatgpt=True)

    assert response.status_code == 503
    assert "error" in response.json()


def test_ask_reports_request_error_as_bad_gateway(client, monkeypatch):
    from apps.assistant.exceptions import AssistantRequestError

    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )

    def _raise(article, question):
        raise AssistantRequestError("сбой сети")

    monkeypatch.setattr("apps.assistant.views.services.answer_question", _raise)

    response = _ask(client, question="вопрос", article_slug=article.slug, use_chatgpt=True)

    assert response.status_code == 502
    assert "error" in response.json()


def test_ask_reports_disabled_as_forbidden(client, settings):
    settings.OPENAI_API_KEY = "test-key"
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article = article_services.create_article(
        title="Статья", content_source="текст", created_by=user
    )
    services.set_assistant_enabled(enabled=False, actor=user)

    response = _ask(client, question="вопрос", article_slug=article.slug, use_chatgpt=True)

    assert response.status_code == 403
    assert "error" in response.json()


def test_toggle_requires_authentication(client):
    response = client.post(reverse("assistant:toggle"), {"assistant_enabled": "on"})
    assert response.status_code == 302


def test_toggle_requires_staff(client):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)

    response = client.post(reverse("assistant:toggle"), {"assistant_enabled": "on"})

    assert response.status_code == 403


def test_toggle_requires_post(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.get(reverse("assistant:toggle"))
    assert response.status_code == 405


def test_staff_can_enable_and_disable_assistant(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.post(reverse("assistant:toggle"), {})
    assert response.status_code == 302
    assert AssistantSettings.get_solo().is_enabled is False
    assert AssistantSettings.get_solo().updated_by == admin

    response = client.post(reverse("assistant:toggle"), {"assistant_enabled": "on"})
    assert response.status_code == 302
    assert AssistantSettings.get_solo().is_enabled is True


def test_toggle_redirects_to_safe_referer(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.post(
        reverse("assistant:toggle"),
        {"assistant_enabled": "on"},
        HTTP_REFERER="http://testserver/some/page/",
    )

    assert response.status_code == 302
    assert response.url == "http://testserver/some/page/"


def test_toggle_ignores_unsafe_referer(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.post(
        reverse("assistant:toggle"),
        {"assistant_enabled": "on"},
        HTTP_REFERER="http://evil.example/",
    )

    assert response.status_code == 302
    assert response.url == reverse("home")


def test_local_ai_admin_requires_authentication(client):
    response = client.get(reverse("assistant:local_ai_admin"))
    assert response.status_code == 302


def test_local_ai_admin_requires_staff(client):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)

    response = client.get(reverse("assistant:local_ai_admin"))

    assert response.status_code == 403


def test_local_ai_admin_shows_status_for_staff(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.get(reverse("assistant:local_ai_admin"))

    assert response.status_code == 200


def test_retrain_requires_staff(client, monkeypatch):
    user = UserFactory(must_change_password=False, is_staff=False)
    client.force_login(user)
    called = []
    monkeypatch.setattr(
        "apps.assistant.views.training.retrain_local_model", lambda **kw: called.append(kw)
    )

    response = client.post(reverse("assistant:retrain_local_ai"))

    assert response.status_code == 403
    assert called == []


def test_retrain_requires_post(client):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    response = client.get(reverse("assistant:retrain_local_ai"))
    assert response.status_code == 405


def test_retrain_calls_training_and_redirects(client, monkeypatch):
    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)
    called = []
    monkeypatch.setattr(
        "apps.assistant.views.training.retrain_local_model",
        lambda **kw: called.append(kw),
    )

    response = client.post(reverse("assistant:retrain_local_ai"))

    assert response.status_code == 302
    assert response.url == reverse("assistant:local_ai_admin")
    assert called == [{"actor": admin}]


def test_retrain_reports_already_training_without_crashing(client, monkeypatch):
    from apps.assistant import training

    admin = UserFactory(must_change_password=False, is_staff=True)
    client.force_login(admin)

    def _raise(**kwargs):
        raise training.LocalAiAlreadyTrainingError("Обучение уже выполняется.")

    monkeypatch.setattr("apps.assistant.views.training.retrain_local_model", _raise)

    response = client.post(reverse("assistant:retrain_local_ai"))

    assert response.status_code == 302
    assert response.url == reverse("assistant:local_ai_admin")
