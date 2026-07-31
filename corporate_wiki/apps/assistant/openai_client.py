"""Thin wrapper around the OpenAI SDK.

Isolated in its own module for two reasons: tests monkeypatch this
function instead of mocking the SDK client directly, and nothing else in
the app needs to import ``openai`` or know how the client is constructed.
"""

from __future__ import annotations

from django.conf import settings

from apps.assistant.exceptions import AssistantNotConfiguredError, AssistantRequestError


def _client():
    if not settings.OPENAI_API_KEY:
        raise AssistantNotConfiguredError("ИИ-ассистент не настроен: не задан OPENAI_API_KEY.")
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY)


def create_chat_completion(*, system_prompt: str, user_prompt: str) -> str:
    try:
        response = _client().chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
    except AssistantNotConfiguredError:
        raise
    except Exception as exc:
        raise AssistantRequestError(f"Не удалось получить ответ от ИИ: {exc}") from exc
    return response.choices[0].message.content or ""


def create_json_chat_completion(*, system_prompt: str, user_prompt: str) -> str:
    """Same as create_chat_completion, but constrains the model to return
    a syntactically valid JSON object (OpenAI's JSON mode) -- used where
    the response needs to be parsed programmatically (see
    apps.assistant.chunking_remote) rather than shown to a person as-is.
    """
    try:
        response = _client().chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
    except AssistantNotConfiguredError:
        raise
    except Exception as exc:
        raise AssistantRequestError(f"Не удалось получить ответ от ИИ: {exc}") from exc
    return response.choices[0].message.content or ""
