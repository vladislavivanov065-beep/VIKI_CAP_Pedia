import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore

from apps.accounts import services
from apps.accounts.factories import UserFactory

pytestmark = pytest.mark.django_db


def _create_session_for(user):
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session.save()
    return session


def test_reset_user_password_by_admin_forces_change_and_stamps_timestamp():
    admin = UserFactory(is_staff=True, is_superuser=True)
    user = UserFactory(must_change_password=False)

    services.reset_user_password_by_admin(
        user=user, new_temporary_password="NewTemp0rary!99", actor=admin
    )
    user.refresh_from_db()

    assert user.must_change_password is True
    assert user.password_reset_by_admin_at is not None
    assert user.check_password("NewTemp0rary!99")


def test_reset_user_password_by_admin_invalidates_only_that_users_sessions():
    admin = UserFactory(is_staff=True, is_superuser=True)
    target = UserFactory()
    other = UserFactory()

    target_session = _create_session_for(target)
    other_session = _create_session_for(other)

    services.reset_user_password_by_admin(
        user=target, new_temporary_password="NewTemp0rary!99", actor=admin
    )

    assert not SessionStore().exists(target_session.session_key)
    assert SessionStore().exists(other_session.session_key)


def test_change_user_password_clears_must_change_password():
    user = UserFactory(must_change_password=True)
    services.change_user_password(user=user, new_password="BrandNewPass!42")
    user.refresh_from_db()

    assert user.must_change_password is False
    assert user.password_changed_at is not None
    assert user.check_password("BrandNewPass!42")


def test_deactivate_user_invalidates_sessions_and_blocks_login():
    admin = UserFactory(is_staff=True, is_superuser=True)
    user = UserFactory()
    session = _create_session_for(user)

    services.deactivate_user(user=user, actor=admin)
    user.refresh_from_db()

    assert user.is_active is False
    assert not SessionStore().exists(session.session_key)
