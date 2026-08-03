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
        lambda **_: json.dumps({"new_fragment_starts": [4]}),
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
        return json.dumps({"new_fragment_starts": [2]})

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


def test_remote_group_into_chunks_ignores_an_out_of_range_boundary(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    text = "Первая строка.\nВторая строка."

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": [99]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result == ["Первая строка.\nВторая строка."]


def test_remote_group_into_chunks_ignores_duplicate_and_non_integer_boundaries(
    settings, monkeypatch
):
    settings.OPENAI_API_KEY = "test-key"
    text = "Первая строка.\nВторая строка.\nТретья строка."

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": [3, 3, "не число"]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result == ["Первая строка.\nВторая строка.", "Третья строка."]


def test_remote_group_into_chunks_never_lets_a_single_bad_boundary_ruin_the_whole_response(
    settings, monkeypatch
):
    # A mostly-correct but slightly sloppy response (duplicate, out of
    # range, and a stray non-integer mixed in with two good boundaries)
    # must still produce the two good boundaries, not fall back entirely.
    settings.OPENAI_API_KEY = "test-key"
    text = "Строка 1.\nСтрока 2.\nСтрока 3.\nСтрока 4.\nСтрока 5."

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": [3, 3, 99, "oops", 5]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result == ["Строка 1.\nСтрока 2.", "Строка 3.\nСтрока 4.", "Строка 5."]


def test_remote_group_into_chunks_falls_back_to_one_fragment_on_an_empty_response(
    settings, monkeypatch
):
    settings.OPENAI_API_KEY = "test-key"
    text = "Первая строка.\nВторая строка."

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": []}),
    )

    assert chunking_remote.remote_group_into_chunks(text) == ["Первая строка.\nВторая строка."]


def test_remote_group_into_chunks_falls_back_on_invalid_json(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"
    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: "не json",
    )

    result = chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.")

    assert result is None


def test_remote_group_into_chunks_caps_an_oversized_fragment(settings, monkeypatch):
    # The model returns no boundaries at all for a 30-line article -- a
    # real risk if it judges the whole thing "one topic". No fragment
    # should end up longer than chunking_remote._MAX_FRAGMENT_LINES.
    settings.OPENAI_API_KEY = "test-key"
    lines = [f"Строка {i}." for i in range(1, 31)]
    text = "\n".join(lines)

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": []}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert "\n".join(lines) == "\n".join(result)  # nothing lost or reordered
    assert all(
        fragment.count("\n") + 1 <= chunking_remote._MAX_FRAGMENT_LINES for fragment in result
    )
    assert len(result) > 1


def test_remote_group_into_chunks_caps_only_the_oversized_fragment(settings, monkeypatch):
    # A real boundary from the model in the middle of a long run should
    # survive capping untouched -- only the still-too-long side gets split
    # further.
    settings.OPENAI_API_KEY = "test-key"
    lines = [f"Строка {i}." for i in range(1, 21)]
    text = "\n".join(lines)

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion",
        lambda **_: json.dumps({"new_fragment_starts": [11]}),
    )

    result = chunking_remote.remote_group_into_chunks(text)

    assert result[0] == "\n".join(lines[:10])
    assert all(
        fragment.count("\n") + 1 <= chunking_remote._MAX_FRAGMENT_LINES for fragment in result
    )


def test_cap_fragment_sizes_splits_a_long_run_evenly():
    result = chunking_remote._cap_fragment_sizes([], total_lines=30)

    assert result == [13, 25]


def test_cap_fragment_sizes_leaves_a_short_run_alone():
    assert chunking_remote._cap_fragment_sizes([], total_lines=5) == []


def test_cap_fragment_sizes_keeps_existing_boundaries():
    result = chunking_remote._cap_fragment_sizes([5, 20], total_lines=40)

    assert 5 in result
    assert 20 in result


def test_remote_group_into_chunks_falls_back_when_the_request_fails(settings, monkeypatch):
    settings.OPENAI_API_KEY = "test-key"

    def _raise(**_kwargs):
        raise AssistantRequestError("недоступно")

    monkeypatch.setattr(
        "apps.assistant.chunking_remote.openai_client.create_json_chat_completion", _raise
    )

    result = chunking_remote.remote_group_into_chunks("Первая строка.\nВторая строка.")

    assert result is None
