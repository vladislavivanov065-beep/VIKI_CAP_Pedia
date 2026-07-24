import json

import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.assistant.services import AnswerResult

pytestmark = pytest.mark.django_db


def test_ask_requires_authentication(client):
    response = client.post(
        reverse("assistant:ask"),
        data=json.dumps({"question": "вопрос"}),
        content_type="application/json",
    )
    assert response.status_code == 302


def test_ask_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("assistant:ask"))
    assert response.status_code == 405


def test_ask_rejects_empty_question(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(
        reverse("assistant:ask"),
        data=json.dumps({"question": "  "}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_ask_rejects_malformed_json(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.post(
        reverse("assistant:ask"), data="not json", content_type="application/json"
    )
    assert response.status_code == 400


def test_ask_returns_answer_and_sources(client, monkeypatch):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    fake_article = type("FakeArticle", (), {"title": "Отпуска", "slug": "otpuska"})()
    monkeypatch.setattr(
        "apps.assistant.views.services.answer_question",
        lambda question: AnswerResult(answer="Ответ на вопрос.", sources=[fake_article]),
    )

    response = client.post(
        reverse("assistant:ask"),
        data=json.dumps({"question": "Как оформить отпуск?"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Ответ на вопрос."
    assert data["sources"] == [{"title": "Отпуска", "slug": "otpuska"}]


def test_ask_reports_not_configured_as_service_unavailable(client, monkeypatch):
    from apps.assistant.exceptions import AssistantNotConfiguredError

    user = UserFactory(must_change_password=False)
    client.force_login(user)

    def _raise(question):
        raise AssistantNotConfiguredError("не настроено")

    monkeypatch.setattr("apps.assistant.views.services.answer_question", _raise)

    response = client.post(
        reverse("assistant:ask"),
        data=json.dumps({"question": "вопрос"}),
        content_type="application/json",
    )

    assert response.status_code == 503
    assert "error" in response.json()


def test_ask_reports_request_error_as_bad_gateway(client, monkeypatch):
    from apps.assistant.exceptions import AssistantRequestError

    user = UserFactory(must_change_password=False)
    client.force_login(user)

    def _raise(question):
        raise AssistantRequestError("сбой сети")

    monkeypatch.setattr("apps.assistant.views.services.answer_question", _raise)

    response = client.post(
        reverse("assistant:ask"),
        data=json.dumps({"question": "вопрос"}),
        content_type="application/json",
    )

    assert response.status_code == 502
    assert "error" in response.json()
