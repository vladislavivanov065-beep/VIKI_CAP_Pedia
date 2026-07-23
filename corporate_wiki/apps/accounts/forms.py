from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.throttle import is_locked_out, record_failed_attempt, reset_attempts


class EmailAuthenticationForm(AuthenticationForm):
    """Login form: email + password + "remember me", no username field."""

    remember_me = forms.BooleanField(required=False, initial=False, label="Запомнить меня")

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Неверный email или пароль.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget = forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "email"}
        )

    def clean(self):
        raw_email = self.cleaned_data.get("username") or self.data.get("username", "")
        normalized_email = raw_email.strip().lower()
        if normalized_email:
            # Authenticate against the normalized address so login is
            # case-insensitive, matching how emails are stored.
            self.cleaned_data["username"] = normalized_email

        if normalized_email and is_locked_out(normalized_email):
            raise forms.ValidationError(
                "Слишком много неудачных попыток входа. Попробуйте позже.",
                code="locked_out",
            )

        try:
            cleaned_data = super().clean()
        except forms.ValidationError:
            if normalized_email:
                record_failed_attempt(normalized_email)
            raise

        if normalized_email:
            reset_attempts(normalized_email)
        return cleaned_data


class ForcedPasswordChangeForm(PasswordChangeForm):
    """Password change form used both for the mandatory first change and
    for voluntary self-service changes.

    Delegates the actual write to ``services.change_user_password`` so the
    ``must_change_password``/``password_changed_at`` bookkeeping always
    happens together with the password hash update.
    """

    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_same_as_old": "Новый пароль не должен совпадать с текущим (временным) паролем.",
    }

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
            services.change_user_password(
                user=self.user, new_password=self.cleaned_data["new_password1"]
            )
        return self.user
