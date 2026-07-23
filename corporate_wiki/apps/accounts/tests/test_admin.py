import pytest
from django.urls import reverse

from apps.accounts.factories import UserFactory
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client_logged_in(client):
    admin = UserFactory(is_staff=True, is_superuser=True, must_change_password=False)
    client.force_login(admin)
    return client, admin


def test_admin_can_create_user_with_temporary_password(admin_client_logged_in):
    admin_client, _admin = admin_client_logged_in

    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {
            "username": "newperson",
            "first_name": "",
            "last_name": "",
            "temporary_password1": "TempPassw0rd!77",
            "temporary_password2": "TempPassw0rd!77",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    created = User.objects.get(username="newperson")
    assert created.must_change_password is True
    assert created.check_password("TempPassw0rd!77")
    assert created.first_name == ""
    assert created.last_name == ""


def test_admin_add_form_rejects_mismatched_temporary_passwords(admin_client_logged_in):
    admin_client, _admin = admin_client_logged_in

    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {
            "username": "mismatch",
            "temporary_password1": "TempPassw0rd!77",
            "temporary_password2": "SomethingElse!88",
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="mismatch").exists()


def test_admin_set_temporary_password_view_forces_change_and_logs_out_sessions(
    admin_client_logged_in,
):
    admin_client, admin = admin_client_logged_in
    target = UserFactory(must_change_password=False)

    response = admin_client.post(
        reverse("admin:accounts_user_set_temporary_password", args=[target.pk]),
        {
            "new_temporary_password1": "AdminSet0Pass!23",
            "new_temporary_password2": "AdminSet0Pass!23",
        },
    )

    assert response.status_code == 302
    target.refresh_from_db()
    assert target.must_change_password is True
    assert target.password_reset_by_admin_at is not None
    assert target.check_password("AdminSet0Pass!23")


def test_admin_change_form_has_no_password_field(admin_client_logged_in):
    admin_client, _admin = admin_client_logged_in
    target = UserFactory()

    response = admin_client.get(reverse("admin:accounts_user_change", args=[target.pk]))

    assert response.status_code == 200
    assert "temporary_password" not in response.content.decode()
    assert "Установить новый временный пароль" in response.content.decode()
