import pytest
from django.urls import reverse

from apps.accounts.factories import DEFAULT_TEST_PASSWORD, UserFactory
from apps.accounts.throttle import MAX_ATTEMPTS

pytestmark = pytest.mark.django_db


def test_login_with_correct_credentials_succeeds(client):
    UserFactory(email="worker@example.com", must_change_password=False)

    response = client.post(
        reverse("accounts:login"),
        {"username": "worker@example.com", "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert client.session.get("_auth_user_id") is not None


def test_login_page_shows_configured_site_name_not_request_host(client, settings):
    settings.SITE_NAME = "Тестовая база знаний"

    response = client.get(reverse("accounts:login"))

    content = response.content.decode()
    assert "Тестовая база знаний" in content
    assert "testserver" not in content


def test_login_is_case_insensitive_on_email(client):
    UserFactory(email="worker@example.com", must_change_password=False)

    response = client.post(
        reverse("accounts:login"),
        {"username": "Worker@Example.com", "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 302


def test_login_wrong_password_shows_generic_error(client):
    UserFactory(email="worker@example.com")

    response = client.post(
        reverse("accounts:login"),
        {"username": "worker@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 200
    assert "Неверный email или пароль." in response.content.decode()


def test_login_nonexistent_email_shows_same_generic_error(client):
    response = client.post(
        reverse("accounts:login"),
        {"username": "nobody@example.com", "password": "whatever-1234"},
    )

    assert response.status_code == 200
    assert "Неверный email или пароль." in response.content.decode()


def test_login_deactivated_user_is_blocked(client):
    UserFactory(email="inactive@example.com", is_active=False)

    response = client.post(
        reverse("accounts:login"),
        {"username": "inactive@example.com", "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 200
    assert client.session.get("_auth_user_id") is None


def test_repeated_failed_logins_lock_the_email_out(client):
    UserFactory(email="worker@example.com")

    for _ in range(MAX_ATTEMPTS):
        client.post(
            reverse("accounts:login"),
            {"username": "worker@example.com", "password": "wrong-password"},
        )

    response = client.post(
        reverse("accounts:login"),
        {"username": "worker@example.com", "password": DEFAULT_TEST_PASSWORD},
    )

    assert "Слишком много неудачных попыток" in response.content.decode()


def test_successful_login_resets_failed_attempt_counter(client):
    UserFactory(email="worker@example.com", must_change_password=False)

    client.post(
        reverse("accounts:login"),
        {"username": "worker@example.com", "password": "wrong-password"},
    )
    response = client.post(
        reverse("accounts:login"),
        {"username": "worker@example.com", "password": DEFAULT_TEST_PASSWORD},
    )

    assert response.status_code == 302


def test_no_self_service_password_reset_routes_exist(client):
    response = client.get("/password/reset/")
    assert response.status_code == 404


def test_login_page_has_no_password_reset_link(client):
    response = client.get(reverse("accounts:login"))
    assert "password/reset" not in response.content.decode()
    assert "обратитесь к администратору" in response.content.decode()
