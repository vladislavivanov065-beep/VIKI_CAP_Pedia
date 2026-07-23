from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy

from apps.accounts.forms import EmailAuthenticationForm, ForcedPasswordChangeForm


class EmailLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return response

    def get_success_url(self):
        if self.request.user.must_change_password:
            return reverse_lazy("accounts:password_change")
        return super().get_success_url()


class ForcedPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = ForcedPasswordChangeForm
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Пароль успешно изменён.")
        return response
