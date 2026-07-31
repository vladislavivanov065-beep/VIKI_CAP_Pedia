"""Finds the article sentences most relevant to a question, without any
external service. Pure word-overlap scoring (TF-IDF-weighted, lemmatized
via pymorphy3 for Russian words and stemmed via a Porter stemmer for
English ones, so both match across inflected forms) -- no network calls
(both run entirely offline, no corpus download), so this always works
even when OpenAI isn't configured or has been disabled by an
administrator.
"""

from __future__ import annotations

import functools
import math
import re
import threading
from collections import Counter

import pymorphy3
from nltk.stem import PorterStemmer

from apps.assistant.text_utils import split_sentences

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)

_morph: pymorphy3.MorphAnalyzer | None = None
_morph_lock = threading.Lock()
_stemmer = PorterStemmer()

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


def _get_morph() -> pymorphy3.MorphAnalyzer:
    global _morph
    if _morph is None:
        with _morph_lock:
            if _morph is None:
                _morph = pymorphy3.MorphAnalyzer()
    return _morph


@functools.lru_cache(maxsize=20000)
def _lemma(word: str) -> str:
    if _CYRILLIC_RE.search(word):
        return _get_morph().parse(word)[0].normal_form
    return _stemmer.stem(word)


def _keywords(tokens: list[str]) -> list[str]:
    return [_lemma(t) for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _score_candidates(candidates: list[str], question: str) -> list[float]:
    """TF-IDF-weighted keyword overlap of each candidate text against the
    question, using lemmatized words so e.g. "рекламу"/"рекламы" count as
    the same keyword. A score of 0 means the candidate shares no meaningful
    (non-stopword) lemma with the question at all.
    """
    query_keywords = set(_keywords(_tokenize(question)))
    if not candidates or not query_keywords:
        return [0.0] * len(candidates)

    candidate_keywords = [_keywords(_tokenize(c)) for c in candidates]

    document_frequency: Counter[str] = Counter()
    for keywords in candidate_keywords:
        document_frequency.update(set(keywords))

    total = len(candidates)
    idf = {
        word: math.log((total + 1) / (document_frequency[word] + 1)) + 1 for word in query_keywords
    }

    scores: list[float] = []
    for keywords in candidate_keywords:
        if not keywords:
            scores.append(0.0)
            continue
        term_frequency = Counter(keywords)
        score = sum(
            term_frequency[word] * idf[word] for word in query_keywords if word in term_frequency
        )
        scores.append(score / math.sqrt(len(keywords)) if score > 0 else 0.0)
    return scores


def find_best_sentences(*, text: str, question: str, max_sentences: int = 1) -> list[str]:
    """Ranks the article's sentences by TF-IDF overlap with the question's
    keywords and returns the top matches, in their original order. Returns
    an empty list if none of the question's meaningful words appear
    anywhere in the text.
    """
    sentences = split_sentences(text)
    scores = _score_candidates(sentences, question)

    scored = [(score, index) for index, score in enumerate(scores) if score > 0]
    if not scored:
        return []

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_indices = sorted(index for _score, index in scored[:max_sentences])
    return [sentences[i] for i in top_indices]


def pick_best_sentence(*, sentences: list[str], question: str) -> str | None:
    """Reranks a small set of pre-selected candidate sentences (typically
    the top embedding matches for a question, see apps.assistant.local_ai)
    by lemmatized keyword overlap. Returns None -- rather than the least-bad
    candidate -- when not one of them shares a meaningful word with the
    question, since callers fall back to the top embedding match in that
    case instead of a lexically arbitrary pick.
    """
    scores = _score_candidates(sentences, question)
    best_index = max(range(len(sentences)), key=lambda i: scores[i], default=None)
    if best_index is None or scores[best_index] <= 0:
        return None
    return sentences[best_index]
