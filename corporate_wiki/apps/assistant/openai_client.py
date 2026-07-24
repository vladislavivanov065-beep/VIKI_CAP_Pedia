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
