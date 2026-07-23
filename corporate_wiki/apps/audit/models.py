from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """An immutable record of a security-relevant action (section 12.7).

    Deliberately has no ``ip_address`` field — the spec forbids using the
    client IP for rate limiting, blocking, audit, or identification
    anywhere in this project.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "запись аудита"
        verbose_name_plural = "записи аудита"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Записи аудита нельзя изменять после создания.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Записи аудита нельзя удалять.")
