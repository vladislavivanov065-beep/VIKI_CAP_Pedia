from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from apps.audit.models import AuditLog

if TYPE_CHECKING:
    from apps.accounts.models import User


def record_event(
    *,
    actor: User | None,
    action: str,
    object_type: str = "",
    object_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    user_agent: str = "",
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        metadata=metadata or {},
        user_agent=(user_agent or "")[:500],
    )
