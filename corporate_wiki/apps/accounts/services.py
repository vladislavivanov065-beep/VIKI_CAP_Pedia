"""Business logic for user accounts.

Views and admin forms call into this module instead of touching models
directly, per the project's service-layer rule (see TЗ section 13).

Every security-relevant action here is recorded twice: once to the
``security`` logger (section 18) and once as an immutable ``AuditLog``
row (section 12.7/Stage 9). Callers pass ``user_agent`` when they have a
request to read it from; it defaults to empty for management commands.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.services import record_event

security_logger = logging.getLogger("security")


def _log_security_event(
    action: str,
    actor: User | None,
    target: User | None,
    *,
    user_agent: str = "",
    **metadata: Any,
) -> None:
    security_logger.info(
        "%s actor=%s target=%s metadata=%s",
        action,
        actor.username if actor else None,
        target.username if target else None,
        metadata,
    )
    record_event(
        actor=actor,
        action=action,
        object_type="user",
        object_id=target.pk if target else None,
        metadata={k: str(v) for k, v in metadata.items()},
        user_agent=user_agent,
    )


def create_user_with_temporary_password(
    *,
    username: str,
    temporary_password: str,
    first_name: str = "",
    last_name: str = "",
    is_staff: bool = False,
    is_superuser: bool = False,
    created_by: User | None = None,
    user_agent: str = "",
) -> User:
    """Create a new user; ``must_change_password`` defaults to True.

    ``first_name``/``last_name`` may be left blank — an administrator is
    allowed to create a user with no name on file.
    """
    user = User.objects.create_user(
        username=username,
        password=temporary_password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )
    _log_security_event("user.created", actor=created_by, target=user, user_agent=user_agent)
    return user


def update_profile(
    *,
    user: User,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    user_agent: str = "",
) -> User:
    """Self-service update of login/first name/last name.

    All three are optional — pass ``None`` (not an empty string) for any
    field that should be left untouched. An empty string for
    ``first_name``/``last_name`` clears the name; an empty/``None``
    ``username`` never changes the login, since it must stay set for the
    user to be able to log in.
    """
    update_fields = ["updated_at"]
    if username and username != user.username:
        user.username = username
        update_fields.append("username")
    if first_name is not None and first_name != user.first_name:
        user.first_name = first_name
        update_fields.append("first_name")
    if last_name is not None and last_name != user.last_name:
        user.last_name = last_name
        update_fields.append("last_name")

    if len(update_fields) > 1:
        user.full_clean(exclude=["password"])
        user.save(update_fields=update_fields)
        _log_security_event("user.profile_updated", actor=user, target=user, user_agent=user_agent)
    return user


def change_user_password(*, user: User, new_password: str, user_agent: str = "") -> User:
    """Self-service password change after the old password was verified."""
    user.set_password(new_password)
    user.must_change_password = False
    user.password_changed_at = timezone.now()
    user.save(
        update_fields=["password", "must_change_password", "password_changed_at", "updated_at"]
    )
    _log_security_event("user.password_changed", actor=user, target=user, user_agent=user_agent)
    return user


def reset_user_password_by_admin(
    *, user: User, new_temporary_password: str, actor: User, user_agent: str = ""
) -> User:
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
    _log_security_event(
        "user.password_reset_by_admin", actor=actor, target=user, user_agent=user_agent
    )
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


def invalidate_other_sessions(*, user: User, current_session_key: str | None) -> int:
    """Same as ``invalidate_user_sessions`` but keeps the caller's own
    current session alive (section 9.7: "завершить другие активные
    сессии" — the user doing this is still using one of them).
    """
    deleted = 0
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        if session.session_key == current_session_key:
            continue
        data = session.get_decoded()
        if data.get(SESSION_KEY) == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


def set_force_password_change(
    *, user: User, actor: User, value: bool = True, user_agent: str = ""
) -> User:
    """Administrator toggles the forced-password-change flag directly."""
    user.must_change_password = value
    user.save(update_fields=["must_change_password", "updated_at"])
    _log_security_event(
        "user.force_password_change_set",
        actor=actor,
        target=user,
        user_agent=user_agent,
        value=value,
    )
    return user


def deactivate_user(*, user: User, actor: User, user_agent: str = "") -> User:
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    invalidate_user_sessions(user)
    _log_security_event("user.deactivated", actor=actor, target=user, user_agent=user_agent)
    return user


def activate_user(*, user: User, actor: User, user_agent: str = "") -> User:
    user.is_active = True
    user.save(update_fields=["is_active", "updated_at"])
    _log_security_event("user.activated", actor=actor, target=user, user_agent=user_agent)
    return user
