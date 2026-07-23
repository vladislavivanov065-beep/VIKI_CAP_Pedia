import pytest
from django.urls import reverse

from apps.accounts.factories import DEFAULT_TEST_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def test_anonymous_user_is_redirected_to_login():
    from django.test import Client

    client = Client()
    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_forced_password_change_user_is_redirected_away_from_home(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_change")


def test_forced_password_change_user_can_reach_password_change_page(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = client.get(reverse("accounts:password_change"))

    assert response.status_code == 200


def test_forced_password_change_user_can_reach_logout(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = client.post(reverse("accounts:logout"))

    assert response.status_code in (200, 302)


def test_forced_password_change_cannot_be_bypassed_via_admin(client):
    user = UserFactory(must_change_password=True, is_staff=True, is_superuser=True)
    client.force_login(user)

    response = client.get("/admin/")

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_change")


def test_after_changing_password_user_can_reach_home(client):
    user = UserFactory(must_change_password=True)
    client.force_login(user)

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": DEFAULT_TEST_PASSWORD,
            "new_password1": "BrandNewPass!42",
            "new_password2": "BrandNewPass!42",
        },
    )
    assert response.status_code == 302

    home_response = client.get(reverse("home"))
    assert home_response.status_code == 200
