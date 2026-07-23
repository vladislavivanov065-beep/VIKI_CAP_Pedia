from django.contrib.auth.views import LogoutView
from django.urls import path

from apps.accounts.views import EmailLoginView, ForcedPasswordChangeView

app_name = "accounts"

urlpatterns = [
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/change/", ForcedPasswordChangeView.as_view(), name="password_change"),
]
