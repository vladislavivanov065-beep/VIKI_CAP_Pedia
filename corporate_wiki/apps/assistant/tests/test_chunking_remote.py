import json

import pytest

from apps.assistant import chunking_remote
from apps.assistant.exceptions import AssistantRequestError
from apps.assistant.models import AssistantSettings

pytestmark = pytest.mark.django_db


def test_remote_group_into_chunks_returns_none_without_an_api_key(settings):
    settings.OPENAI_API_KEY = ""

    assert chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.") is None


def test_remote_group_into_chunks_returns_none_when_assistant_disabled(settings):
    settings.OPENAI_API_KEY = "test-key"
    solo = AssistantSettings.get_solo()
    solo.is_enabled = False
    solo.save(update_fields=["is_enabled"])

    assert chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.") is None


def test_remote_group_into_chunks_skips_the_api_call_for_a_single_line(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    called = []
    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: called.append(1),
    )

    result = chunking_remote.remote_group_into_chunks("Единственная строка.")

    assert result == ["Единственная строка."]
    assert called == []


def test_remote_group_into_chunks_builds_fragments_from_the_original_lines(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    text = (
        "Случаи, при которых возможен овердрафт.\n"
        "Первый случай.\nВторой случай.\nОтдельный абзац."
    )

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"groups": [[1, 2, 3], [4]]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result == [
        "Случаи, при которых возможен овердрафт.\nПервый случай.\nВторой случай.",
        "Отдельный абзац.",
    ]


def test_remote_group_into_chunks_never_sends_the_real_sensitive_values(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    text = "BIN 493711 Singapore.\nЛимит 30,000 в день."
    captured = {}

    def fake_create_json_chat_completion(*, system_prompt, user_prompt):
        captured["user_prompt"] = user_prompt
        return json.dumps({"groups": [[1], [2]]})

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        fake_create_json_chat_completion,
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert "493711" not in captured["user_prompt"]
    assert "Singapore" not in captured["user_prompt"]
    assert "30,000" not in captured["user_prompt"]
    # But the real values are still in the fragments actually stored/indexed.
    assert result == ["BIN 493711 Singapore.", "Лимит 30,000 в день."]


def test_remote_group_into_chunks_orders_fragments_by_original_position(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    text = "Первая строка.\nВторая строка."

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        # Groups returned out of order -- output must still follow the article.
        lambda **_: json.dumps({"groups": [[2], [1]]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result == ["Первая строка.", "Вторая строка."]


def test_remote_group_into_chunks_falls_back_on_invalid_json(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: "не json",
    )

    result = chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.")

    assert result is None


@pytest.mark.parametrize(
    "groups",
    [
        [[1]],  # missing line 2
        [[1, 2], [2]],  # duplicate line 2
        [[1, 2, 3]],  # out-of-range line 3
        [],  # empty
        [[1], []],  # empty group
    ],
)
def test_remote_group_into_chunks_falls_back_on_an_invalid_partition(settings, monkeypatch, groups):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"groups": groups}),
    )

    result = chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.")

    assert result is None


def test_remote_group_into_chunks_falls_back_when_the_request_fails(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"

    def _raise(**_kwargs):
        raise AssistantRequestError("недоступно")

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion", _raise
    )

    result = chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.")

    assert result is None
