from __future__ import annotations

from django.conf import settings
from django.db import models


class AssistantSettings(models.Model):
    """Site-wide on/off switch for the AI assistant, controlled by an
    administrator from the sidebar (see apps.assistant.views.toggle).

    A singleton row (see get_solo) rather than a settings.py value,
    because it needs to be flippable at runtime by an admin without a
    redeploy. When disabled, nobody can send a question to OpenAI --
    including someone who already had their own per-question checkbox
    checked, or who tries the endpoint directly.
    """

    is_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = "настройки ИИ-ассистента"
        verbose_name_plural = "настройки ИИ-ассистента"

    def __str__(self) -> str:
        return "ИИ-ассистент включён" if self.is_enabled else "ИИ-ассистент выключен"

    @classmethod
    def get_solo(cls) -> AssistantSettings:
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
