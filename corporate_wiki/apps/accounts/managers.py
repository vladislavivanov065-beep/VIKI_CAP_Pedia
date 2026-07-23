from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

if TYPE_CHECKING:
    from apps.accounts.models import User


class UserManager(BaseUserManager["User"]):
    """Manager for the email-only custom user model."""

    use_in_migrations = True

    @staticmethod
    def normalize_email_value(email: str) -> str:
        """Strip surrounding whitespace and lower-case the whole address.

        Django's own ``normalize_email`` only lower-cases the domain part;
        the spec requires the entire address to be case-insensitive.
        """
        if not email:
            raise ValueError("Email обязателен")
        return email.strip().lower()

    def _create_user(self, email: str, password: str | None, **extra_fields: Any) -> User:
        email = self.normalize_email_value(email)
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValueError("Некорректный формат email") from exc

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self._create_user(email, password, **extra_fields)
