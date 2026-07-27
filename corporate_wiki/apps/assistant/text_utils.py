"""Plain-text extraction shared by the OpenAI, local-search, and local-AI
answer paths -- all three need the same "article HTML -> plain text"
conversion.
"""

from __future__ import annotations

import re
from html import unescape

from apps.articles.models import Article

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def article_plain_text(article: Article) -> str:
    revision = article.current_revision
    html = revision.content_html if revision else ""
    text = unescape(_TAG_RE.sub(" ", html or ""))
    return _WHITESPACE_RE.sub(" ", text).strip()
