import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_unknown_url_renders_custom_404_page(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    response = client.get("/this-page-does-not-exist/")

    assert response.status_code == 404
    assert "Страница не найдена" in response.content.decode()


def test_anonymous_hitting_unknown_url_gets_404_not_a_data_leak():
    from django.test import Client

    response = Client().get("/this-page-does-not-exist/")

    # A route that doesn't exist never resolves to a view, so it never
    # reaches LoginRequiredMiddleware — it 404s directly, which reveals
    # nothing about protected content either way.
    assert response.status_code == 404


def test_anonymous_user_accessing_a_real_protected_url_is_redirected_to_login():
    from django.test import Client

    response = Client().get(reverse("home"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
