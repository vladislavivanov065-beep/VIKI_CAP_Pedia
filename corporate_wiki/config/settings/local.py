"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS as _ALLOWED_HOSTS
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = _ALLOWED_HOSTS or ["localhost", "127.0.0.1"]

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
