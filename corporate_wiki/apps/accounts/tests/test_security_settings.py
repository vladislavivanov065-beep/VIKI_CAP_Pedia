import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse

from apps.accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_security_settings_requires_authentication(client):
    response = client.get(reverse("accounts:security_settings"))
    assert response.status_code == 302


def test_security_settings_page_renders(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("accounts:security_settings"))
    assert response.status_code == 200
    assert "Безопасность" in response.content.decode()


def test_terminate_other_sessions_keeps_current_session_alive(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    other_session = SessionStore()
    other_session[SESSION_KEY] = str(user.pk)
    other_session.save()

    response = client.post(reverse("accounts:terminate_other_sessions"))

    assert response.status_code == 302
    assert not SessionStore().exists(other_session.session_key)
    # The current session (used by `client` itself) must still work.
    follow_up = client.get(reverse("accounts:security_settings"))
    assert follow_up.status_code == 200


def test_terminate_other_sessions_requires_post(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("accounts:terminate_other_sessions"))
    assert response.status_code == 405


def test_security_settings_updates_username_and_names(client):
    user = UserFactory(must_change_password=False, username="worker", first_name="", last_name="")
    client.force_login(user)

    response = client.post(
        reverse("accounts:security_settings"),
        {"username": "worker.new", "first_name": "Иван", "last_name": "Иванов"},
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.username == "worker.new"
    assert user.first_name == "Иван"
    assert user.last_name == "Иванов"


def test_security_settings_rejects_blank_username(client):
    user = UserFactory(must_change_password=False, username="worker")
    client.force_login(user)

    response = client.post(
        reverse("accounts:security_settings"),
        {"username": "", "first_name": "", "last_name": ""},
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.username == "worker"


def test_security_settings_rejects_username_already_taken(client):
    UserFactory(username="taken")
    user = UserFactory(must_change_password=False, username="worker")
    client.force_login(user)

    response = client.post(
        reverse("accounts:security_settings"),
        {"username": "taken", "first_name": "", "last_name": ""},
    )

    assert response.status_code == 200
    assert "уже занят" in response.content.decode()
    user.refresh_from_db()
    assert user.username == "worker"


def test_sidebar_no_longer_links_profile_pages(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get(reverse("home"))
    content = response.content.decode()
    assert "Мой профиль" not in content
    assert "Настройки профиля" not in content
    assert "Безопасность" in content
