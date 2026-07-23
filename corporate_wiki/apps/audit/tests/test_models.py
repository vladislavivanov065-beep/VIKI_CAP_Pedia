import pytest

from apps.accounts.factories import UserFactory
from apps.audit.models import AuditLog
from apps.audit.services import record_event

pytestmark = pytest.mark.django_db


def test_record_event_creates_row_without_ip_field():
    user = UserFactory()
    entry = record_event(actor=user, action="user.login", user_agent="pytest-agent")

    assert entry.actor == user
    assert entry.action == "user.login"
    assert entry.user_agent == "pytest-agent"
    assert not hasattr(entry, "ip_address")


def test_audit_log_cannot_be_updated():
    entry = record_event(actor=None, action="user.login_failed")
    entry.action = "tampered"
    with pytest.raises(ValueError):
        entry.save()


def test_audit_log_cannot_be_deleted():
    entry = record_event(actor=None, action="user.login_failed")
    with pytest.raises(ValueError):
        entry.delete()


def test_audit_log_survives_actor_deactivation_reference():
    user = UserFactory()
    entry = record_event(actor=user, action="user.created", metadata={"email": user.email})
    assert AuditLog.objects.get(pk=entry.pk).actor == user


def test_metadata_defaults_to_empty_dict():
    entry = record_event(actor=None, action="user.login_failed")
    assert entry.metadata == {}
