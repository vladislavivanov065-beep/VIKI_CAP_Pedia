from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from apps.accounts.models import User


class UserManager(BaseUserManager["User"]):
    """Manager for the username-based custom user model."""

    use_in_migrations = True

    @staticmethod
    def normalize_username_value(username: str) -> str:
        """Strip surrounding whitespace and lower-case the login.

        Usernames are restricted to ASCII, so plain ``str.lower()`` is
        safe here (unlike SQLite's ``LOWER()``, which only folds ASCII —
        see the notes on Cyrillic title matching elsewhere in this repo).
        """
        if not username:
            raise ValueError("Логин обязателен")
        return username.strip().lower()

    def _create_user(self, username: str, password: str | None, **extra_fields: Any) -> User:
        username = self.normalize_username_value(username)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, username: str, password: str | None = None, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(
        self, username: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self._create_user(username, password, **extra_fields)
