from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.accounts.services import invalidate_user_sessions


class Command(BaseCommand):
    help = "Terminate every active session belonging to the given user's email."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str)

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise CommandError(f"Пользователь с email {email} не найден.") from exc

        count = invalidate_user_sessions(user)
        self.stdout.write(
            self.style.SUCCESS(f"Завершено сессий: {count} (пользователь {user.email}).")
        )
