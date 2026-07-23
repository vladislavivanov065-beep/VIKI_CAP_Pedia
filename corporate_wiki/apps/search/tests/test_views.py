import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.articles import services as article_services

pytestmark = pytest.mark.django_db


def test_search_results_page_requires_authentication(client):
    response = client.get(reverse("search:search"), {"q": "test"})
    assert response.status_code == 302


def test_search_results_page_shows_matching_articles(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article_services.create_article(
        title="Отпускные правила", content_source="текст", created_by=user
    )

    response = client.get(reverse("search:search"), {"q": "Отпускные"})
    content = response.content.decode()
    assert response.status_code == 200
    assert "Отпускные правила" in content


def test_search_results_page_handles_no_matches(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("search:search"), {"q": "ничегошеничего"})
    assert response.status_code == 200
    assert "Ничего не найдено" in response.content.decode()


def test_search_results_page_without_query_shows_prompt(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("search:search"))
    assert response.status_code == 200
    assert "Введите поисковый запрос" in response.content.decode()


def test_suggestions_endpoint_returns_json(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article_services.create_article(title="Командировки", content_source="x", created_by=user)

    response = client.get(reverse("search:suggestions"), {"q": "команд"})
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"][0]["title"] == "Командировки"
    assert "url" in data["suggestions"][0]


def test_suggestions_endpoint_requires_authentication(client):
    response = client.get(reverse("search:suggestions"), {"q": "команд"})
    assert response.status_code == 302


def test_suggestions_endpoint_empty_for_short_query(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)
    article_services.create_article(title="Командировки", content_source="x", created_by=user)

    response = client.get(reverse("search:suggestions"), {"q": "к"})
    assert response.json()["suggestions"] == []
