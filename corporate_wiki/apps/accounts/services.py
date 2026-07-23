"""Business logic for user accounts.

Views and admin forms call into this module instead of touching models
directly, per the project's service-layer rule (see TЗ section 13).

Audit logging here is a thin ``logging``-based placeholder (section 18)
until the ``AuditLog`` model lands in Stage 9, at which point these calls
will also persist a row instead of only writing to the security log.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.accounts.models import User

security_logger = logging.getLogger("security")


def _log_security_event(
    action: str, actor: User | None, target: User | None, **metadata: Any
) -> None:
    security_logger.info(
        "%s actor=%s target=%s metadata=%s",
        action,
        actor.email if actor else None,
        target.email if target else None,
        metadata,
    )


def create_user_with_temporary_password(
    *,
    email: str,
    temporary_password: str,
    first_name: str = "",
    last_name: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    created_by: User | None = None,
) -> User:
    """Create a new user; ``must_change_password`` defaults to True."""
    user = User.objects.create_user(
        email=email,
        password=temporary_password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    _log_security_event("user.created", actor=created_by, target=user)
    return user


def change_user_password(*, user: User, new_password: str) -> User:
    """Self-service password change after the old password was verified."""
    user.set_password(new_password)
    user.must_change_password = False
    user.password_changed_at = timezone.now()
    user.save(
        update_fields=["password", "must_change_password", "password_changed_at", "updated_at"]
    )
    _log_security_event("user.password_changed", actor=user, target=user)
    return user


def reset_user_password_by_admin(*, user: User, new_temporary_password: str, actor: User) -> User:
    """Administrator sets a new temporary password for another user.

    Forces a mandatory password change on next login and terminates every
    existing session of that user. The plaintext temporary password is
    never persisted anywhere — only its hash, via ``set_password``.
    """
    user.set_password(new_temporary_password)
    user.must_change_password = True
    user.password_reset_by_admin_at = timezone.now()
    user.save(
        update_fields=[
            "password",
            "must_change_password",
            "password_reset_by_admin_at",
            "updated_at",
        ]
    )
    invalidate_user_sessions(user)
    _log_security_event("user.password_reset_by_admin", actor=actor, target=user)
    return user


def invalidate_user_sessions(user: User) -> int:
    """Delete every active session belonging to ``user``.

    The default DB-backed session store has no direct user foreign key, so
    sessions are matched by decoding their payload.
    """
    deleted = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if data.get(SESSION_KEY) == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


def set_force_password_change(*, user: User, actor: User, value: bool = True) -> User:
    """Administrator toggles the forced-password-change flag directly."""
    user.must_change_password = value
    user.save(update_fields=["must_change_password", "updated_at"])
    _log_security_event("user.force_password_change_set", actor=actor, target=user, value=value)
    return user


def deactivate_user(*, user: User, actor: User) -> User:
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    invalidate_user_sessions(user)
    _log_security_event("user.deactivated", actor=actor, target=user)
    return user


def activate_user(*, user: User, actor: User) -> User:
    user.is_active = True
    user.save(update_fields=["is_active", "updated_at"])
    _log_security_event("user.activated", actor=actor, target=user)
    return user
