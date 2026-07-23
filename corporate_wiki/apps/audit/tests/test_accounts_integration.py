import pytest

from apps.accounts import services
from apps.accounts.factories import UserFactory
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


def test_create_user_with_temporary_password_is_audited():
    admin = UserFactory(is_staff=True, is_superuser=True)

    user = services.create_user_with_temporary_password(
        email="new@example.com",
        temporary_password="TempPassw0rd!77",
        created_by=admin,
        user_agent="pytest-agent",
    )

    entry = AuditLog.objects.get(action="user.created", object_id=user.pk)
    assert entry.actor == admin
    assert entry.user_agent == "pytest-agent"


def test_password_reset_by_admin_is_audited():
    admin = UserFactory(is_staff=True, is_superuser=True)
    target = UserFactory()

    services.reset_user_password_by_admin(
        user=target, new_temporary_password="NewTemp0rary!99", actor=admin, user_agent="ua"
    )

    entry = AuditLog.objects.get(action="user.password_reset_by_admin", object_id=target.pk)
    assert entry.actor == admin
    assert entry.user_agent == "ua"


def test_self_service_password_change_is_audited():
    user = UserFactory(must_change_password=True)

    services.change_user_password(user=user, new_password="BrandNewPass!42")

    entry = AuditLog.objects.get(action="user.password_changed", object_id=user.pk)
    assert entry.actor == user


def test_deactivate_and_activate_are_audited():
    admin = UserFactory(is_staff=True, is_superuser=True)
    target = UserFactory()

    services.deactivate_user(user=target, actor=admin)
    services.activate_user(user=target, actor=admin)

    assert AuditLog.objects.filter(action="user.deactivated", object_id=target.pk).exists()
    assert AuditLog.objects.filter(action="user.activated", object_id=target.pk).exists()


def test_admin_password_reset_via_view_is_audited(client):
    admin = UserFactory(is_staff=True, is_superuser=True, must_change_password=False)
    target = UserFactory()
    client.force_login(admin)

    from django.urls import reverse

    response = client.post(
        reverse("admin:accounts_user_set_temporary_password", args=[target.pk]),
        {
            "new_temporary_password1": "AdminSet0Pass!23",
            "new_temporary_password2": "AdminSet0Pass!23",
        },
        HTTP_USER_AGENT="admin-browser/2.0",
    )

    assert response.status_code == 302
    entry = AuditLog.objects.get(action="user.password_reset_by_admin", object_id=target.pk)
    assert entry.actor == admin
    assert entry.user_agent == "admin-browser/2.0"
