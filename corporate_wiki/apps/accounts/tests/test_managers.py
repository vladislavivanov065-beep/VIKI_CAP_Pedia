import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_username():
    user = User.objects.create_user(username="  User.Name ", password="StrongPassw0rd!23")
    assert user.username == "user.name"


def test_create_user_rejects_invalid_username_format():
    with pytest.raises(ValidationError):
        User.objects.create_user(username="имя-с-кириллицей", password="StrongPassw0rd!23")


def test_create_user_requires_username():
    with pytest.raises(ValueError):
        User.objects.create_user(username="", password="StrongPassw0rd!23")


def test_create_superuser_sets_staff_and_superuser_flags():
    admin = User.objects.create_superuser(username="admin", password="StrongPassw0rd!23")
    assert admin.is_staff is True
    assert admin.is_superuser is True


def test_create_superuser_rejects_is_staff_false():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            username="admin2", password="StrongPassw0rd!23", is_staff=False
        )


def test_username_uniqueness_is_case_insensitive():
    User.objects.create_user(username="dup", password="StrongPassw0rd!23")
    with pytest.raises(ValidationError):
        User.objects.create_user(username="DUP", password="StrongPassw0rd!23")
