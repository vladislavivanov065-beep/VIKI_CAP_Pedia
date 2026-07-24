"""Production settings.

Runs behind whatever TLS-terminating infrastructure the host provides —
this project does not ship or assume an Nginx/reverse-proxy layer.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set explicitly in production")

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SECURE_SSL_REDIRECT = True
# This app never terminates TLS itself -- something in front of it always
# does (ngrok, a load balancer, ...) and forwards plain HTTP internally.
# Without this, Django thinks every request is insecure and
# SECURE_SSL_REDIRECT above redirects every single request to itself
# forever, since the browser is already on https and the redirect target
# is identical to the URL it just requested.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
