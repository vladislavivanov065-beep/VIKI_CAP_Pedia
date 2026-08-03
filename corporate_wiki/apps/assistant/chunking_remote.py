"""Uses ChatGPT to decide where one fragment ends and the next begins, as
an alternative to the local embedding-based heuristic in
apps.assistant.chunking -- optional, since the whole point of the local AI
feature is to keep working with no OpenAI configured at all. Used from
apps.assistant.training, which falls back to the local heuristic whenever
this returns None (not configured, disabled, request failed) -- same
degradation pattern as everywhere else in this app that talks to OpenAI.

ChatGPT is only ever asked to *point at existing line numbers*, never to
reproduce any text itself: the article's lines are numbered locally, sent
to the model with anything sensitive replaced by a "[XXXn]" placeholder
(see apps.assistant.redaction) so a card BIN, tariff, or address never
reaches OpenAI, and the model returns only the line numbers where a new
fragment starts. The final fragments are then built directly from the
ORIGINAL, unredacted lines by slicing between those numbers -- there's
nothing to "unredact" in the model's response, because the real text was
never sent to it in the first place.

Deliberately asking for boundary *points*, not a full partition of every
line into groups: an earlier version asked the model to bucket every line
number into a group in one JSON response, which meant a single missed or
duplicated line number anywhere in a long article (150+ lines is a
realistic size here) invalidated the whole response and silently fell
back to the local heuristic every time -- a mistake in a handful of
boundary numbers just shifts a fragment edge slightly instead. There is
no invalid list of boundary numbers short of them not being numbers at
all: out-of-range or duplicate values are simply dropped (see
_clean_boundaries), never treated as a reason to discard everything.
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
    "Определи, на каких строках начинается новый смысловой фрагмент — "
    "например, абзац и вводимый им список или таблица идут одним "
    "фрагментом, а не двумя, значит строка со списком/таблицей НЕ начинает "
    "новый фрагмент. Строка 1 всегда начинает первый фрагмент — не "
    "указывай её. Ответь ТОЛЬКО json-объектом вида "
    '{"new_fragment_starts": [4, 9, 15]} — номера строк, на которых '
    "начинается каждый следующий фрагмент, по возрастанию, без пояснений."
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
        raw_starts = json.loads(response)["new_fragment_starts"]
    except (AssistantNotConfiguredError, AssistantRequestError):
        return None
    except Exception:
        logger.exception("ChatGPT chunking response was not usable JSON, falling back")
        return None

    boundaries = _clean_boundaries(raw_starts, total_lines=len(lines))
    logger.info("ChatGPT chunking: %d line(s) into %d fragment(s)", len(lines), len(boundaries) + 1)

    fragment_edges = [1, *boundaries, len(lines) + 1]
    return [
        "\n".join(lines[start - 1 : end - 1])
        for start, end in zip(fragment_edges[:-1], fragment_edges[1:], strict=True)
    ]


def _clean_boundaries(raw_starts: object, *, total_lines: int) -> list[int]:
    """Keeps only the in-range, non-duplicate line numbers that could
    actually start a fragment (2..total_lines -- line 1 always starts the
    first one). Anything else in the model's response (an out-of-range
    number, a duplicate, a non-integer) is just dropped rather than
    treated as a reason to discard the whole response.
    """
    if not isinstance(raw_starts, list):
        return []
    valid = {start for start in raw_starts if isinstance(start, int) and 2 <= start <= total_lines}
    return sorted(valid)
