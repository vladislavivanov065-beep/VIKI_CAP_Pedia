"""Settings shared by every environment.

Environment-specific files (local.py, test.py, production.py) import
everything from here with ``from .base import *`` and then override only
what actually differs for that environment.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
# Needed to submit any form (e.g. login) when the site is reachable through
# a tunnel/reverse proxy on a different origin than ALLOWED_HOSTS alone
# would suggest to a browser (ngrok, a custom domain in front of Docker,
# etc.) — Django's CSRF check compares the request's Origin/Referer
# against this list for HTTPS requests.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.articles",
    "apps.images",
    "apps.attachments",
    "apps.search",
    "apps.assistant",
    "apps.audit",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "apps.accounts.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.site_settings",
                "apps.assistant.context_processors.assistant_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database — SQLite only. The file lives on a persistent Docker volume so it
# survives container restarts and rebuilds.
# ---------------------------------------------------------------------------
SQLITE_PATH = env("SQLITE_PATH", default=str(BASE_DIR / "data" / "db.sqlite3"))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH,
    }
}

# Where `manage.py backup_database` writes its snapshots (section 25,
# Этап 11.6). Defaults to a sibling directory of the database file itself.
BACKUP_DIR = env("BACKUP_DIR", default=str(Path(SQLITE_PATH).parent / "backups"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files — served by WhiteNoise. User-uploaded images are NOT static
# files: they live in SQLite and are served through a dedicated view.
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Project-level settings driven by environment variables (see .env.example).
# The site name/branding is intentionally never hard-coded in templates.
# ---------------------------------------------------------------------------
SITE_NAME = env("SITE_NAME", default="Corporate Wiki")
SITE_URL = env("SITE_URL", default="http://localhost:8000")

MAX_IMAGE_SIZE_MB = env.int("MAX_IMAGE_SIZE_MB", default=10)
MAX_IMAGE_WIDTH = env.int("MAX_IMAGE_WIDTH", default=8000)
MAX_IMAGE_HEIGHT = env.int("MAX_IMAGE_HEIGHT", default=8000)

MAX_ATTACHMENT_SIZE_MB = env.int("MAX_ATTACHMENT_SIZE_MB", default=20)

# "Задай свой вопрос" (apps.assistant) -- answers a question about the
# article currently being viewed via OpenAI, called only at the moment a
# question is actually asked (never on save). Left blank, the feature
# degrades to a clear "не настроено" message instead of failing hard
# (see apps.assistant.services.answer_question).
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_CHAT_MODEL = env("OPENAI_CHAT_MODEL", default="gpt-4o-mini")

# Bootstrap credentials for `manage.py create_initial_admin` only. Never
# logged, never stored anywhere except as a hashed password.
ADMIN_USERNAME = env("ADMIN_USERNAME", default="")
ADMIN_TEMP_PASSWORD = env("ADMIN_TEMP_PASSWORD", default="")

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
