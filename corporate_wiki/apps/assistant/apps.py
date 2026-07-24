from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    label = "assistant"
    verbose_name = "ИИ-ассистент"

    def ready(self):
        from apps.assistant import signals  # noqa: F401
