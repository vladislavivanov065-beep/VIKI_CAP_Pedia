import pytest

from apps.accounts.factories import UserFactory
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_display_name_falls_back_to_email_when_names_blank():
    user = UserFactory(first_name="", last_name="", email="Nameless@Example.com")
    assert user.display_name == "nameless@example.com"


def test_display_name_uses_full_name_when_available():
    user = UserFactory(first_name="Иван", last_name="Иванов")
    assert user.display_name == "Иван Иванов"


def test_get_short_name_falls_back_to_email():
    user = UserFactory(first_name="", last_name="")
    assert user.get_short_name() == user.email


def test_email_is_normalized_on_save():
    user = UserFactory(email="  Mixed.Case@Example.COM  ")
    user.refresh_from_db()
    assert user.email == "mixed.case@example.com"


def test_new_user_defaults_to_must_change_password_true():
    user = User.objects.create_user(email="fresh@example.com", password="StrongPassw0rd!23")
    assert user.must_change_password is True


def test_user_has_no_job_title_department_or_avatar_fields():
    field_names = {f.name for f in User._meta.get_fields()}
    assert "job_title" not in field_names
    assert "department" not in field_names
    assert "avatar" not in field_names
