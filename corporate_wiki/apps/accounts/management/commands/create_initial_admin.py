from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import services
from apps.accounts.models import User


class Command(BaseCommand):
    help = (
        "Bootstrap the first administrator from ADMIN_USERNAME/ADMIN_TEMP_PASSWORD. "
        "Does nothing if a superuser already exists."
    )

    def handle(self, *args, **options):
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("Суперпользователь уже существует, ничего не делаю.")
            return

        username = settings.ADMIN_USERNAME
        temporary_password = settings.ADMIN_TEMP_PASSWORD

        if not username or not temporary_password:
            raise CommandError(
                "ADMIN_USERNAME и ADMIN_TEMP_PASSWORD должны быть заданы " "в переменных окружения."
            )

        transient_user = User(username=username.strip().lower())
        try:
            validate_password(temporary_password, user=transient_user)
        except ValidationError as exc:
            raise CommandError("Ненадёжный ADMIN_TEMP_PASSWORD: " + " ".join(exc.messages)) from exc

        user = services.create_user_with_temporary_password(
            username=username,
            temporary_password=temporary_password,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Создан первый администратор {user.username}. "
                "При первом входе потребуется сменить временный пароль."
            )
        )
