"""Plain-text extraction shared by the OpenAI, local-search, and local-AI
answer paths -- all three need the same "article HTML -> plain text"
conversion and sentence splitting.
"""

from __future__ import annotations

import re
from html import unescape

from apps.articles.models import Article

_TAG_RE = re.compile(r"<[^>]+>")

# A heading, paragraph, list, table row, or line break ends whatever came
# before it whether or not that text itself ended in punctuation (e.g. a
# heading, or a table cell). Without turning these into an explicit line
# break, article_plain_text would run everything together into one
# "sentence" with no punctuation between an unrelated heading/list and the
# next paragraph -- see split_sentences, which treats a line break the
# same as a period.
_HARD_BREAK_RE = re.compile(
    r"</(?:p|h[1-6]|ul|ol|table|tr|blockquote|div)\s*>|<br\s*/?>", re.IGNORECASE
)
# A list item or table cell ends *within* its list/row, but joining
# consecutive ones onto their own line each (e.g. "хостинги" / "домены" /
# "нейросети" one per line) would let a matching answer come back as a
# single item with no context -- join them with commas onto one line
# instead, and let _HARD_BREAK_RE's </ul>/</table>/</tr> end that line.
_SOFT_BREAK_RE = re.compile(r"</(?:li|td|th)\s*>", re.IGNORECASE)

_TRAILING_JOINER_RE = re.compile(r"[,;]\s*$")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def article_plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    # Collapse the renderer's own pretty-printing whitespace (including
    # newlines between e.g. <li> elements) *before* inserting our own
    # \n markers below, so those are the only newlines left to split on.
    flattened = _WHITESPACE_RE.sub(" ", html or "")
    with_breaks = _HARD_BREAK_RE.sub("\n", _SOFT_BREAK_RE.sub(", ", flattened))
    text = unescape(_TAG_RE.sub(" ", with_breaks))

    lines = []
    for line in text.split("\n"):
        line = _TRAILING_JOINER_RE.sub("", _WHITESPACE_RE.sub(" ", line).strip())
        if line:
            lines.append(line)
    return "\n".join(lines)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
