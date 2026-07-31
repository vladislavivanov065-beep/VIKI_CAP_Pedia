"""Plain-text extraction shared by the OpenAI, local-search, and local-AI
answer paths -- all three need the same "article HTML -> plain text"
conversion and sentence splitting.
"""

from __future__ import annotations

import re
from html import unescape

from apps.articles.models import Article

_TAG_RE = re.compile(r"<[^>]+>")

# A paragraph or heading immediately followed by a list/table is
# introducing it -- "Случаи, при которых возможен овердрафт." followed by
# a bullet list of those cases is one answer, not two. Left alone, the
# paragraph would become its own sentence and the list its own separate
# one (see _SOFT_BREAK_RE below), so a question matching the intro
# sentence would retrieve it *without* the cases it's introducing.
# Suppressing the break here merges them into a single retrievable unit
# instead: joining them with a space is enough since the intro almost
# always already ends in its own punctuation ("." or ":").
_SUPPRESSED_BREAK_RE = re.compile(r"</(?:p|h[1-6])>\s*(?=<(?:ul|ol|table)\b)", re.IGNORECASE)

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
_BLOCK_SPLIT_RE = re.compile(r"\n+")


def article_plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    # Collapse the renderer's own pretty-printing whitespace (including
    # newlines between e.g. <li> elements) *before* inserting our own
    # \n markers below, so those are the only newlines left to split on.
    flattened = _WHITESPACE_RE.sub(" ", html or "")
    not_split_before_list = _SUPPRESSED_BREAK_RE.sub(" ", flattened)
    with_breaks = _HARD_BREAK_RE.sub("\n", _SOFT_BREAK_RE.sub(", ", not_split_before_list))
    text = unescape(_TAG_RE.sub(" ", with_breaks))

    lines = []
    for line in text.split("\n"):
        line = _TRAILING_JOINER_RE.sub("", _WHITESPACE_RE.sub(" ", line).strip())
        if line:
            lines.append(line)
    return "\n".join(lines)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def split_blocks(text: str) -> list[str]:
    """Splits only on the block boundaries article_plain_text draws
    (paragraph/heading/list/table/line break), *not* on sentence-ending
    punctuation within one -- unlike split_sentences. Used for local AI
    indexing (apps.assistant.training) so a paragraph that introduces a
    list or table stays one retrievable unit together with it, rather
    than being split apart at its own "." the way split_sentences would.
    """
    return [b.strip() for b in _BLOCK_SPLIT_RE.split(text) if b.strip()]
