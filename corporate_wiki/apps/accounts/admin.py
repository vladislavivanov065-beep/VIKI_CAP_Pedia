from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse

from apps.accounts import services
from apps.accounts.models import User


class AdminUserCreationForm(forms.ModelForm):
    """Admin "add user" form: sets a temporary password, not password1/2."""

    temporary_password1 = forms.CharField(label="Временный пароль", widget=forms.PasswordInput)
    temporary_password2 = forms.CharField(
        label="Подтверждение временного пароля", widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "is_active", "is_staff", "is_superuser"]

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("temporary_password1")
        password2 = cleaned_data.get("temporary_password2")

        if password1 and password2 and password1 != password2:
            self.add_error("temporary_password2", "Пароли не совпадают.")

        if password1:
            transient_user = User(
                email=cleaned_data.get("email", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
            )
            try:
                validate_password(password1, user=transient_user)
            except ValidationError as exc:
                self.add_error("temporary_password1", exc)

        return cleaned_data


class AdminUserChangeForm(forms.ModelForm):
    """Admin "edit user" form. Deliberately has no password field at all —
    password changes only ever go through the dedicated
    "Установить новый временный пароль" view/service.
    """

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "must_change_password",
            "groups",
            "user_permissions",
        ]


class SetTemporaryPasswordForm(forms.Form):
    new_temporary_password1 = forms.CharField(
        label="Новый временный пароль", widget=forms.PasswordInput
    )
    new_temporary_password2 = forms.CharField(
        label="Подтверждение нового временного пароля", widget=forms.PasswordInput
    )

    def __init__(self, *args, target_user: User | None = None, **kwargs):
        self.target_user = target_user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("new_temporary_password1")
        password2 = cleaned_data.get("new_temporary_password2")

        if password1 and password2 and password1 != password2:
            self.add_error("new_temporary_password2", "Пароли не совпадают.")

        if password1 and self.target_user is not None:
            try:
                validate_password(password1, user=self.target_user)
            except ValidationError as exc:
                self.add_error("new_temporary_password1", exc)

        return cleaned_data


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    model = User

    list_display = [
        "email",
        "display_name",
        "is_active",
        "is_staff",
        "must_change_password",
        "created_at",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "must_change_password"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]
    filter_horizontal = ["groups", "user_permissions"]

    readonly_fields = [
        "id",
        "last_login",
        "password_changed_at",
        "password_reset_by_admin_at",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (None, {"fields": ("email",)}),
        ("Личные данные", {"fields": ("first_name", "last_name")}),
        (
            "Права доступа",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (
            "Пароль",
            {
                "fields": (
                    "must_change_password",
                    "password_changed_at",
                    "password_reset_by_admin_at",
                )
            },
        ),
        ("Служебная информация", {"fields": ("id", "last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "temporary_password1",
                    "temporary_password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:
            created_user = services.create_user_with_temporary_password(
                email=form.cleaned_data["email"],
                temporary_password=form.cleaned_data["temporary_password1"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                is_staff=form.cleaned_data.get("is_staff", False),
                is_superuser=form.cleaned_data.get("is_superuser", False),
                created_by=request.user,
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            # `obj` is the transient instance built by the ModelForm; point it
            # at the row the service actually created so the rest of the
            # admin's add-view flow (message, redirect, m2m save) targets it.
            obj.pk = created_user.pk
            obj.id = created_user.id
        else:
            obj.save()

    def get_urls(self):
        custom_urls = [
            path(
                "<uuid:object_id>/set-temporary-password/",
                self.admin_site.admin_view(self.set_temporary_password_view),
                name="accounts_user_set_temporary_password",
            ),
        ]
        return custom_urls + super().get_urls()

    def set_temporary_password_view(self, request: HttpRequest, object_id: str):
        user_obj = get_object_or_404(User, pk=object_id)
        if not self.has_change_permission(request, user_obj):
            raise PermissionDenied
        assert isinstance(request.user, User)  # guaranteed by admin_view()'s permission check

        if request.method == "POST":
            form = SetTemporaryPasswordForm(request.POST, target_user=user_obj)
            if form.is_valid():
                services.reset_user_password_by_admin(
                    user=user_obj,
                    new_temporary_password=form.cleaned_data["new_temporary_password1"],
                    actor=request.user,
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                self.message_user(
                    request,
                    "Новый временный пароль установлен. Все сессии пользователя завершены.",
                )
                return redirect(reverse("admin:accounts_user_change", args=[user_obj.pk]))
        else:
            form = SetTemporaryPasswordForm(target_user=user_obj)

        context = {
            **self.admin_site.each_context(request),
            "title": "Установить новый временный пароль",
            "form": form,
            "original": user_obj,
            "opts": self.model._meta,
        }
        return render(request, "admin/accounts/user/set_temporary_password.html", context)
