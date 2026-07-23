"""Login/logout/login-failed are audited via Django's own auth signals
instead of threading logging calls through every auth view — these
signals fire from ``django.contrib.auth.login()``/``logout()``/
``authenticate()`` no matter which view triggers them.
"""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.audit.services import record_event


def _user_agent(request) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    record_event(actor=user, action="user.login", user_agent=_user_agent(request))


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    record_event(actor=user, action="user.logout", user_agent=_user_agent(request))


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username", "")
    record_event(
        actor=None,
        action="user.login_failed",
        metadata={"username": username},
        user_agent=_user_agent(request),
    )
