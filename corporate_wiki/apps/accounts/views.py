from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from apps.accounts import services
from apps.accounts.forms import ForcedPasswordChangeForm, ProfileForm, UsernameAuthenticationForm


class AccountLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = UsernameAuthenticationForm
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # LoginView injects site_name from django.contrib.sites (or a
        # RequestSite fallback whose name is just request.get_host())
        # unconditionally — override it with our own configured value.
        context["site_name"] = settings.SITE_NAME
        return context


class ForcedPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = ForcedPasswordChangeForm
    success_url = reverse_lazy("home")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.request = self.request
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Пароль успешно изменён.")
        return response


def security_settings(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user)
        if form.is_valid():
            form.save(user_agent=request.META.get("HTTP_USER_AGENT", ""))
            messages.success(request, "Данные профиля обновлены.")
            return redirect("accounts:security_settings")
    else:
        form = ProfileForm(user=request.user)
    return render(request, "accounts/security_settings.html", {"profile_form": form})


@require_POST
def terminate_other_sessions(request):
    count = services.invalidate_other_sessions(
        user=request.user, current_session_key=request.session.session_key
    )
    messages.success(request, f"Завершено других сессий: {count}.")
    return redirect("accounts:security_settings")
