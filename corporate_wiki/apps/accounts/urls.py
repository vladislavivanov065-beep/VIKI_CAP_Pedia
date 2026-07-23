from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts.views import (
    AccountLoginView,
    ForcedPasswordChangeView,
    security_settings,
    terminate_other_sessions,
)

app_name = "accounts"

urlpatterns = [
    path("login/", AccountLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/change/", ForcedPasswordChangeView.as_view(), name="password_change"),
    path("settings/security/", security_settings, name="security_settings"),
    path(
        "settings/security/terminate-others/",
        terminate_other_sessions,
        name="terminate_other_sessions",
    ),
]
