from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.validators import ASCIIUsernameValidator

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.throttle import is_locked_out, record_failed_attempt, reset_attempts


class UsernameAuthenticationForm(AuthenticationForm):
    """Login form: username (login) + password + "remember me"."""

    remember_me = forms.BooleanField(required=False, initial=False, label="Запомнить меня")

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Неверный логин или пароль.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Логин"
        self.fields["username"].widget = forms.TextInput(
            attrs={"autofocus": True, "autocomplete": "username"}
        )

    def clean(self):
        raw_username = self.cleaned_data.get("username") or self.data.get("username", "")
        normalized_username = raw_username.strip().lower()
        if normalized_username:
            # Authenticate against the normalized login so sign-in is
            # case-insensitive, matching how usernames are stored.
            self.cleaned_data["username"] = normalized_username

        if normalized_username and is_locked_out(normalized_username):
            raise forms.ValidationError(
                "Слишком много неудачных попыток входа. Попробуйте позже.",
                code="locked_out",
            )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            if normalized_username:
                record_failed_attempt(normalized_username)
            raise

        if normalized_username:
            reset_attempts(normalized_username)
        return cleaned_data


class ForcedPasswordChangeForm(PasswordChangeForm):
    """Password change form used both for the mandatory first change and
    for voluntary self-service changes.

    Delegates the password write to ``services.change_user_password`` so
    the ``must_change_password``/``password_changed_at`` bookkeeping
    always happens together with the password hash update. Also offers
    optional login/first name/last name changes on the same screen — all
    three are optional; leaving the login blank keeps the current one.
    """

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_same_as_old": "Новый пароль не должен совпадать с текущим (временным) паролем.",
    }

    username = forms.CharField(
        label="Логин",
        max_length=150,
        required=False,
        validators=[ASCIIUsernameValidator()],
        help_text="Оставьте пустым, чтобы не менять текущий логин.",
    )
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)

    field_order = [
        "old_password",
        "new_password1",
        "new_password2",
        "username",
        "first_name",
        "last_name",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip().lower()
        if not username:
            return ""
        if username != self.user.username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Такой логин уже занят.", code="username_taken")
        return username

    def clean_new_password1(self):
        new_password1 = self.cleaned_data.get("new_password1")
        old_password = self.cleaned_data.get("old_password")
        if new_password1 and old_password and new_password1 == old_password:
            raise forms.ValidationError(
                self.error_messages["password_same_as_old"],
                code="password_same_as_old",
            )
        return new_password1

    def save(self, commit: bool = True) -> User:
        if commit:
            request = getattr(self, "request", None)
            user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
            services.change_user_password(
                user=self.user,
                new_password=self.cleaned_data["new_password1"],
                user_agent=user_agent,
            )
            services.update_profile(
                user=self.user,
                username=self.cleaned_data.get("username") or None,
                first_name=self.cleaned_data.get("first_name"),
                last_name=self.cleaned_data.get("last_name"),
                user_agent=user_agent,
            )
        return self.user


class ProfileForm(forms.Form):
    """Editing login/first name/last name from the Security settings page."""

    username = forms.CharField(label="Логин", max_length=150, validators=[ASCIIUsernameValidator()])
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        kwargs.setdefault(
            "initial",
            {
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
        )
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip().lower()
        if not username:
            raise forms.ValidationError("Логин не может быть пустым.", code="username_required")
        if username != self.user.username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Такой логин уже занят.", code="username_taken")
        return username

    def save(self, *, user_agent: str = "") -> User:
        return services.update_profile(
            user=self.user,
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            user_agent=user_agent,
        )
