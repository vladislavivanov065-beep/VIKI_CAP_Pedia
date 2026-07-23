import pytest
from django.urls import reverse

from apps.accounts.factories import DEFAULT_TEST_PASSWORD, UserFactory
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_successful_login_is_recorded(client):
    UserFactory(username="worker", must_change_password=False)

    client.post(
        reverse("accounts:login"),
        {"username": "worker", "password": DEFAULT_TEST_PASSWORD},
        HTTP_USER_AGENT="pytest-browser/1.0",
    )

    entry = AuditLog.objects.filter(action="user.login").latest("created_at")
    assert entry.actor.username == "worker"
    assert entry.user_agent == "pytest-browser/1.0"


def test_failed_login_is_recorded_without_identifying_a_user():
    from django.test import Client

    Client().post(
        reverse("accounts:login"),
        {"username": "nobody", "password": "wrong"},
    )

    entry = AuditLog.objects.filter(action="user.login_failed").latest("created_at")
    assert entry.actor is None
    assert entry.metadata.get("username") == "nobody"


def test_logout_is_recorded(client):
    user = UserFactory(must_change_password=False)
    client.force_login(user)

    client.post(reverse("accounts:logout"))

    entry = AuditLog.objects.filter(action="user.logout").latest("created_at")
    assert entry.actor == user
