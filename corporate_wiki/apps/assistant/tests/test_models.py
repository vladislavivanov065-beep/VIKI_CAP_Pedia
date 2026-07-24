import pytest

from apps.assistant.models import AssistantSettings

pytestmark = pytest.mark.django_db


def test_get_solo_creates_row_enabled_by_default():
    solo = AssistantSettings.get_solo()

    assert solo.is_enabled is True
    assert AssistantSettings.objects.count() == 1


def test_get_solo_returns_the_same_row_on_repeated_calls():
    first = AssistantSettings.get_solo()
    first.is_enabled = False
    first.save(update_fields=["is_enabled"])

    second = AssistantSettings.get_solo()

    assert second.pk == first.pk
    assert second.is_enabled is False
    assert AssistantSettings.objects.count() == 1
