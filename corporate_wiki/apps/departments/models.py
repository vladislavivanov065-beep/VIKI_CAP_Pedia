"""The unit of the org-structure access control (see apps.articles.
visibility): every user optionally belongs to one Department
(apps.accounts.models.User.department), and every article can optionally
be restricted to a set of departments (apps.articles.models.Article.
visible_departments). Both assignments are managed entirely through
Django Admin -- there's no dedicated app UI for either, by design (see
README).
"""

from __future__ import annotations

import uuid

from django.db import models


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = "подразделение"
        verbose_name_plural = "подразделения"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
