import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.assistant.models import AssistantSettings

pytestmark = pytest.mark.django_db


def test_warm_up_local_ai_skips_loading_models_when_never_trained(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.assistant.local_models.embed_texts", lambda *a, **k: calls.append("embed")
    )
    monkeypatch.setattr(
        "apps.assistant.local_models.score_pairs", lambda *a, **k: calls.append("score")
    )

    call_command("warm_up_local_ai")

    assert calls == []


def test_warm_up_local_ai_loads_both_models_once_trained(monkeypatch):
    solo = AssistantSettings.get_solo()
    solo.local_ai_trained_at = timezone.now()
    solo.save(update_fields=["local_ai_trained_at"])

    calls = []
    monkeypatch.setattr(
        "apps.assistant.local_models.embed_texts", lambda *a, **k: calls.append(("embed", a, k))
    )
    monkeypatch.setattr(
        "apps.assistant.local_models.score_pairs", lambda *a, **k: calls.append(("score", a, k))
    )

    call_command("warm_up_local_ai")

    assert [call[0] for call in calls] == ["embed", "score"]


def test_warm_up_local_ai_does_not_raise_when_a_model_fails_to_load(monkeypatch):
    solo = AssistantSettings.get_solo()
    solo.local_ai_trained_at = timezone.now()
    solo.save(update_fields=["local_ai_trained_at"])

    def _raise(*_args, **_kwargs):
        raise RuntimeError("нет сети")

    monkeypatch.setattr("apps.assistant.local_models.embed_texts", _raise)

    # Must not raise -- a deploy shouldn't fail over a model that's still
    # reachable most of the time, and the whole point of graceful
    # degradation elsewhere in this app is that a question still works
    # without local AI, just slower / via a different fallback.
    call_command("warm_up_local_ai")
