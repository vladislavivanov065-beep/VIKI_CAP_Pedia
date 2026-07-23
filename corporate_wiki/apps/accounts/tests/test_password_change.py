import pytest
from django.urls import reverse

from apps.accounts.factories import DEFAULT_TEST_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def _post_change(client, old, new1, new2, **extra):
    return client.post(
        reverse("accounts:password_change"),
        {"old_password": old, "new_password1": new1, "new_password2": new2, **extra},
    )


def test_new_password_same_as_temporary_password_is_rejected(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = _post_change(
        client, DEFAULT_TEST_PASSWORD, DEFAULT_TEST_PASSWORD, DEFAULT_TEST_PASSWORD
    )

    assert response.status_code == 200
    assert "не должен совпадать" in response.content.decode()
    user.refresh_from_db()
    assert user.must_change_password is True


def test_password_shorter_than_minimum_length_is_rejected(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = _post_change(client, DEFAULT_TEST_PASSWORD, "Short1!", "Short1!")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.must_change_password is True


def test_fully_numeric_password_is_rejected(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = _post_change(client, DEFAULT_TEST_PASSWORD, "123456789012", "123456789012")

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.must_change_password is True


def test_successful_change_clears_forced_flag_and_stamps_timestamp(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = _post_change(client, DEFAULT_TEST_PASSWORD, "BrandNewPass!42", "BrandNewPass!42")

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.password_changed_at is not None
    assert user.check_password("BrandNewPass!42")


def test_first_login_can_leave_username_and_names_unchanged(client):
    user = UserFactory(must_change_password=True, username="worker", first_name="", last_name="")
    client.force_login(user)

    response = _post_change(client, DEFAULT_TEST_PASSWORD, "BrandNewPass!42", "BrandNewPass!42")

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.username == "worker"
    assert user.first_name == ""
    assert user.last_name == ""


def test_first_login_can_optionally_change_username_and_names(client):
    user = UserFactory(must_change_password=True, username="worker")
    client.force_login(user)

    response = _post_change(
        client,
        DEFAULT_TEST_PASSWORD,
        "BrandNewPass!42",
        "BrandNewPass!42",
        username="new.login",
        first_name="Иван",
        last_name="Иванов",
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert user.username == "new.login"
    assert user.first_name == "Иван"
    assert user.last_name == "Иванов"


def test_first_login_rejects_username_already_taken_by_someone_else(client):
    UserFactory(username="taken")
    user = UserFactory(must_change_password=True, username="worker")
    client.force_login(user)

    response = _post_change(
        client,
        DEFAULT_TEST_PASSWORD,
        "BrandNewPass!42",
        "BrandNewPass!42",
        username="taken",
    )

    assert response.status_code == 200
    assert "уже занят" in response.content.decode()
    user.refresh_from_db()
    assert user.username == "worker"
