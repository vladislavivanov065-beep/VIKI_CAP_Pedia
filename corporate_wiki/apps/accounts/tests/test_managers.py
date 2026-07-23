import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email():
    user = User.objects.create_user(email="  User@Example.COM ", password="StrongPassw0rd!23")
    assert user.email == "user@example.com"


def test_create_user_rejects_invalid_email_format():
    with pytest.raises(ValueError):
        User.objects.create_user(email="not-an-email", password="StrongPassw0rd!23")


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="StrongPassw0rd!23")


def test_create_superuser_sets_staff_and_superuser_flags():
    admin = User.objects.create_superuser(email="admin@example.com", password="StrongPassw0rd!23")
    assert admin.is_staff is True
    assert admin.is_superuser is True


def test_create_superuser_rejects_is_staff_false():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="admin2@example.com", password="StrongPassw0rd!23", is_staff=False
        )


def test_email_uniqueness_is_case_insensitive():
    User.objects.create_user(email="dup@example.com", password="StrongPassw0rd!23")
    with pytest.raises(ValidationError):
        User.objects.create_user(email="DUP@EXAMPLE.COM", password="StrongPassw0rd!23")
