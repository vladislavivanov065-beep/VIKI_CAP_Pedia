"""Finds the article sentences most relevant to a question, without any
external service. Pure word-overlap scoring (TF-IDF-weighted, with a crude
prefix normalization to tolerate Russian inflection) -- no ML model, no
network calls, so this always works even when OpenAI isn't configured or
has been disabled by an administrator.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Common short Russian words that carry no distinguishing meaning for
# matching a question against a sentence.
_STOPWORDS = frozenset(
    {
        "и",
        "в",
        "во",
        "не",
        "что",
        "он",
        "на",
        "я",
        "с",
        "со",
        "как",
        "а",
        "то",
        "все",
        "она",
        "так",
        "его",
        "но",
        "да",
        "ты",
        "к",
        "у",
        "же",
        "вы",
        "за",
        "бы",
        "по",
        "только",
        "ее",
        "мне",
        "было",
        "вот",
        "от",
        "меня",
        "еще",
        "нет",
        "о",
        "из",
        "ему",
        "теперь",
        "когда",
        "даже",
        "ну",
        "вдруг",
        "ли",
        "если",
        "уже",
        "или",
        "ни",
        "быть",
        "был",
        "него",
        "до",
        "вас",
        "нибудь",
        "опять",
        "уж",
        "вам",
        "ведь",
        "там",
        "потом",
        "себя",
        "ничего",
        "ей",
        "может",
        "они",
        "тут",
        "где",
        "есть",
        "надо",
        "ней",
        "для",
        "мы",
        "тебя",
        "их",
        "чем",
        "была",
        "сам",
        "чтоб",
        "без",
        "будто",
        "чего",
        "раз",
        "тоже",
        "себе",
        "под",
        "будет",
        "ж",
        "тогда",
        "кто",
        "этот",
        "того",
        "потому",
        "этого",
        "какой",
        "совсем",
        "ним",
        "здесь",
        "этом",
        "один",
        "почти",
        "мой",
        "тем",
        "чтобы",
        "нее",
        "сейчас",
        "были",
        "куда",
        "зачем",
        "всех",
        "никогда",
        "можно",
        "при",
        "наконец",
        "два",
        "об",
        "другой",
        "хоть",
        "после",
        "над",
        "больше",
        "тот",
        "через",
        "эти",
        "нас",
        "про",
        "всего",
        "них",
        "какая",
        "много",
        "разве",
        "три",
        "эту",
        "моя",
        "впрочем",
        "хорошо",
        "свою",
        "этой",
        "перед",
        "иногда",
        "лучше",
        "чуть",
        "том",
        "нельзя",
        "такой",
        "им",
        "более",
        "всегда",
        "конечно",
        "всю",
        "между",
    }
)


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _normalize(word: str) -> str:
    # A dependency-free stand-in for stemming: Russian inflectional endings
    # are typically short suffixes, so comparing a truncated prefix of each
    # word catches most case/tense/number variants of the same root.
    return word[:5] if len(word) > 6 else word


def _keywords(tokens: list[str]) -> list[str]:
    return [_normalize(t) for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def find_best_sentences(*, text: str, question: str, max_sentences: int = 3) -> list[str]:
    """Ranks the article's sentences by TF-IDF overlap with the question's
    keywords and returns the top matches, in their original order. Returns
    an empty list if none of the question's meaningful words appear
    anywhere in the text.
    """
    sentences = _split_sentences(text)
    query_keywords = set(_keywords(_tokenize(question)))
    if not sentences or not query_keywords:
        return []

    sentence_keywords = [_keywords(_tokenize(s)) for s in sentences]

    document_frequency: Counter[str] = Counter()
    for keywords in sentence_keywords:
        document_frequency.update(set(keywords))

    total_sentences = len(sentences)
    idf = {
        word: math.log((total_sentences + 1) / (document_frequency[word] + 1)) + 1
        for word in query_keywords
    }

    scored: list[tuple[float, int]] = []
    for index, keywords in enumerate(sentence_keywords):
        if not keywords:
            continue
        term_frequency = Counter(keywords)
        score = sum(
            term_frequency[word] * idf[word] for word in query_keywords if word in term_frequency
        )
        if score > 0:
            scored.append((score / math.sqrt(len(keywords)), index))

    if not scored:
        return []

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_indices = sorted(index for _score, index in scored[:max_sentences])
    return [sentences[i] for i in top_indices]
