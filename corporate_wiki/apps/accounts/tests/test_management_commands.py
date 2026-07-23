import pytest
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.factories import UserFactory
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_initial_admin_creates_user_from_settings(settings):
    settings.ADMIN_USERNAME = "bootstrap"
    settings.ADMIN_TEMP_PASSWORD = "Xk9!ecliptic42Zz"

    call_command("create_initial_admin")

    admin = User.objects.get(username="bootstrap")
    assert admin.is_superuser is True
    assert admin.must_change_password is True


def test_create_initial_admin_is_a_noop_if_superuser_already_exists(settings):
    UserFactory(is_superuser=True, is_staff=True)
    settings.ADMIN_USERNAME = "bootstrap"
    settings.ADMIN_TEMP_PASSWORD = "BootstrapPass!99"

    call_command("create_initial_admin")

    assert not User.objects.filter(username="bootstrap").exists()


def test_create_initial_admin_requires_env_vars(settings):
    settings.ADMIN_USERNAME = ""
    settings.ADMIN_TEMP_PASSWORD = ""

    with pytest.raises(CommandError):
        call_command("create_initial_admin")


def test_invalidate_user_sessions_command_terminates_sessions():
    user = UserFactory()
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session.save()

    call_command("invalidate_user_sessions", user.username)

    assert not SessionStore().exists(session.session_key)


def test_invalidate_user_sessions_command_unknown_username_raises():
    with pytest.raises(CommandError):
        call_command("invalidate_user_sessions", "nobody")
