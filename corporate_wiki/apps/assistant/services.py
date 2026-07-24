"""Answers a question about a specific article using that article's text.

Deliberately simple and article-scoped, not a corpus-wide search: the
question box lives on a single article's page, so the article being
viewed already IS the context -- there's no cross-article retrieval, no
embeddings, and nothing to keep in sync when articles are added or
edited. OpenAI is only ever called at the moment someone actually asks a
question, never when an article is created or saved.
"""

from __future__ import annotations

import dataclasses
import re
from html import unescape

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant import openai_client
from apps.assistant.exceptions import AssistantDisabledError, AssistantRequestError
from apps.assistant.models import AssistantSettings

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# A generous safety cap, well under the chat model's context window --
# not a real chunking scheme, just a guard against a pathologically long
# article wasting tokens/cost on a single request.
_MAX_ARTICLE_CHARS = 20000

_SYSTEM_PROMPT = (
    "Ты — ассистент корпоративной базы знаний. Отвечай на вопрос СТРОГО "
    "на основе текста статьи, приведённого ниже. Если в тексте статьи нет "
    "ответа на вопрос, честно скажи, что не нашёл ответ в этой статье — "
    "не придумывай факты и не используй знания извне. Отвечай кратко и "
    "по делу, на русском языке."
)


def _plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    text = unescape(_TAG_RE.sub(" ", html or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclasses.dataclass
class AnswerResult:
    answer: str


def is_assistant_enabled() -> bool:
    return AssistantSettings.get_solo().is_enabled


def set_assistant_enabled(*, enabled: bool, actor: User) -> None:
    solo = AssistantSettings.get_solo()
    solo.is_enabled = enabled
    solo.updated_by = actor
    solo.save(update_fields=["is_enabled", "updated_by", "updated_at"])


def answer_question(*, article: Article, question: str) -> AnswerResult:
    if not is_assistant_enabled():
        raise AssistantDisabledError("ИИ-ассистент отключён администратором.")

    question = question.strip()
    if not question:
        raise AssistantRequestError("Введите вопрос.")

    article_text = _plain_text(article)
    if not article_text:
        return AnswerResult(answer="В этой статье пока нет текста, чтобы ответить на вопрос.")

    if len(article_text) > _MAX_ARTICLE_CHARS:
        article_text = article_text[:_MAX_ARTICLE_CHARS]

    user_prompt = f"Статья «{article.title}»:\n\n{article_text}\n\n---\n\nВопрос: {question}"

    answer = openai_client.create_chat_completion(
        system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt
    )
    return AnswerResult(answer=answer.strip())
