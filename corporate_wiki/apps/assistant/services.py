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

from apps.accounts.models import User
from apps.articles.models import Article
from apps.assistant import local_ai, local_search, openai_client
from apps.assistant.exceptions import AssistantDisabledError, AssistantRequestError
from apps.assistant.models import AssistantSettings
from apps.assistant.text_utils import article_plain_text

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

    article_text = article_plain_text(article)
    if not article_text:
        return AnswerResult(answer="В этой статье пока нет текста, чтобы ответить на вопрос.")

    if len(article_text) > _MAX_ARTICLE_CHARS:
        article_text = article_text[:_MAX_ARTICLE_CHARS]

    user_prompt = f"Статья «{article.title}»:\n\n{article_text}\n\n---\n\nВопрос: {question}"

    answer = openai_client.create_chat_completion(
        system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt
    )
    return AnswerResult(answer=answer.strip())


def answer_question_locally(*, article: Article, question: str) -> AnswerResult:
    """Answers without any OpenAI call, so this is unaffected by
    AssistantSettings.is_enabled and works even when OPENAI_API_KEY isn't
    configured at all.

    Prefers the trained local AI (an embedding model that finds the single
    best-matching sentence across every article, see apps.assistant.local_ai)
    when an administrator has retrained it at least once. Until then, or if
    it fails for any reason, falls back to plain word-overlap search over
    just the current article -- degrading gracefully rather than erroring.
    """
    question = question.strip()
    if not question:
        raise AssistantRequestError("Введите вопрос.")

    smart_answer = local_ai.answer_from_corpus(question=question)
    if smart_answer is not None:
        return AnswerResult(answer=smart_answer)

    article_text = article_plain_text(article)
    if not article_text:
        return AnswerResult(answer="В этой статье пока нет текста, чтобы ответить на вопрос.")

    matches = local_search.find_best_sentences(text=article_text, question=question)
    if not matches:
        return AnswerResult(answer="Не удалось найти ответ на этот вопрос в тексте статьи.")

    return AnswerResult(answer=" ".join(matches))
