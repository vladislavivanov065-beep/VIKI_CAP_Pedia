"""Uses ChatGPT to decide where one fragment ends and the next begins, as
an alternative to the local embedding-based heuristic in
apps.assistant.chunking -- optional, since the whole point of the local AI
feature is to keep working with no OpenAI configured at all. Used from
apps.assistant.training, which falls back to the local heuristic whenever
this returns None (not configured, disabled, request failed, or the
response didn't validate) -- same degradation pattern as everywhere else
in this app that talks to OpenAI.

ChatGPT is only ever asked to *group existing line numbers*, never to
reproduce any text itself: the article's lines are numbered locally, sent
to the model with anything sensitive replaced by a "[XXXn]" placeholder
(see apps.assistant.redaction) so a card BIN, tariff, or address never
reaches OpenAI, and the model returns which line numbers belong in each
fragment. The final fragments are then built directly from the ORIGINAL,
unredacted lines by index -- there's nothing to "unredact" in the model's
response, because the real text was never sent to it in the first place.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

from apps.assistant import openai_client, redaction
from apps.assistant.exceptions import AssistantNotConfiguredError, AssistantRequestError
from apps.assistant.models import AssistantSettings
from apps.assistant.text_utils import split_blocks

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Тебе присылают пронумерованные строки одной статьи корпоративной базы "
    "знаний. Часть данных в них заменена плейсхолдерами вида [XXXn] — это "
    "ожидаемо, не пытайся угадать, что за ними скрыто, и не убирай их. "
    "Раздели строки на смысловые фрагменты: каждый фрагмент — это набор "
    "ИДУЩИХ ПОДРЯД номеров строк, образующих одну законченную мысль "
    "(например, абзац и вводимый им список или таблица — один фрагмент, "
    "а не два). Каждая строка должна попасть ровно в один фрагмент, ни "
    "одна не пропущена и ни одна не продублирована. "
    'Ответь ТОЛЬКО json-объектом вида {"groups": [[1], [2, 3, 4], [5]]}, '
    "без пояснений."
)


def remote_group_into_chunks(text: str) -> list[str] | None:
    if not settings.OPENAI_API_KEY or not AssistantSettings.get_solo().is_enabled:
        return None

    lines = split_blocks(text)
    if len(lines) <= 1:
        return lines

    redacted_lines = split_blocks(redaction.redact(text).text)
    if len(redacted_lines) != len(lines):
        # Redaction only ever replaces spans *within* a line, never merges
        # or splits lines -- if the counts disagree, something unexpected
        # happened and the line numbers below can't be trusted to line up.
        logger.warning("Redaction changed the article's line count, skipping ChatGPT chunking")
        return None

    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(redacted_lines, start=1))

    try:
        response = openai_client.create_json_chat_completion(
            system_prompt=_SYSTEM_PROMPT, user_prompt=numbered
        )
        groups = json.loads(response)["groups"]
    except (AssistantNotConfiguredError, AssistantRequestError):
        return None
    except Exception:
        logger.exception("ChatGPT chunking response was not usable JSON")
        return None

    if not _is_valid_partition(groups, total_lines=len(lines)):
        logger.warning("ChatGPT chunking response failed validation, falling back")
        return None

    ordered_groups = sorted(groups, key=min)
    return ["\n".join(lines[i - 1] for i in group) for group in ordered_groups]


def _is_valid_partition(groups: object, *, total_lines: int) -> bool:
    """Every line 1..total_lines must appear in exactly one group."""
    if not isinstance(groups, list) or not groups:
        return False
    seen: set[int] = set()
    for group in groups:
        if not isinstance(group, list) or not group:
            return False
        for index in group:
            if not isinstance(index, int) or not (1 <= index <= total_lines) or index in seen:
                return False
            seen.add(index)
    return seen == set(range(1, total_lines + 1))
