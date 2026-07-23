"""Per-email login throttling (section 16.3).

Deliberately keyed by email, never by IP — the spec forbids using the
client IP address for rate limiting, blocking, audit or identification.
Relies on Django's default cache (in-process LocMemCache), which is
consistent with running a single Gunicorn worker as required elsewhere in
the spec.
"""

from __future__ import annotations

from django.core.cache import cache

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _cache_key(email: str) -> str:
    return f"login-attempts:{email.strip().lower()}"


def is_locked_out(email: str) -> bool:
    return cache.get(_cache_key(email), 0) >= MAX_ATTEMPTS


def record_failed_attempt(email: str) -> None:
    key = _cache_key(email)
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, LOCKOUT_SECONDS)


def reset_attempts(email: str) -> None:
    cache.delete(_cache_key(email))
