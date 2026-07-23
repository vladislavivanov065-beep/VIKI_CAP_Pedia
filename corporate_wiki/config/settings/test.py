"""Settings used by the pytest suite.

Uses an in-memory SQLite database and a fast password hasher so the suite
stays quick; nothing here should ever be used to serve real traffic.
"""

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key"  # noqa: S105 - not a real secret, test-only
ALLOWED_HOSTS = ["testserver", "localhost"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
