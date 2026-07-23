from __future__ import annotations

import uuid

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.validators import ASCIIUsernameValidator
from django.db import models

from apps.accounts.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user authenticated by username (login), not email.

    Deliberately does NOT have job_title, department or avatar fields —
    those are explicitly out of scope for this project. Usernames are
    restricted to ASCII letters/digits/@/./+/-/_ (``ASCIIUsernameValidator``)
    so that SQLite's ASCII-only case folding stays correct for uniqueness
    and login lookups.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(
        "логин", max_length=150, unique=True, validators=[ASCIIUsernameValidator()]
    )
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    must_change_password = models.BooleanField(default=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    password_reset_by_admin_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    def save(self, *args, **kwargs):
        if self.username:
            self.username = self.username.strip().lower()
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name or self.username

    @property
    def display_name(self) -> str:
        """Full name when known, otherwise fall back to the login."""
        return self.get_full_name() or self.username
