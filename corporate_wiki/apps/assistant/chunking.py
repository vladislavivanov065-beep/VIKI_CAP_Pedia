"""Groups an article's lines/paragraphs into semantically coherent chunks
for local AI indexing -- finer-grained than the whole article, coarser
than a single line, so a multi-line block like a billing address:

    биллинг адрес
    улица такая-то
    город такой то
    пос код такой то

or a paragraph introducing a list ("Случаи, при которых возможен
овердрафт." + the bulleted cases) stays one retrievable unit instead of
being split apart at every line break.

A line is folded into the fragment being built when either:
  - the fragment's last line has no sentence-ending punctuation -- a
    strong sign it's a label/intro rather than a complete thought on its
    own ("биллинг адрес", "Случаи, при которых возможен овердрафт." with
    a trailing ":", a heading), or
  - the line is still semantically close to the fragment so far (cosine
    similarity of their embeddings) even though it *does* end a
    sentence -- catches prose that continues the same idea across a
    line break without an obvious punctuation tell.
Either signal alone is enough (an address's individual lines aren't
necessarily close to each other in embedding space -- "улица" and
"город" are different concepts -- so requiring *both* would miss the
exact case above), capped by _MAX_GROUP_LINES so a long run of
unpunctuated lines can't merge into one unbounded blob.
"""

from __future__ import annotations

import re

from apps.assistant import local_models
from apps.assistant.text_utils import split_blocks

_TERMINAL_PUNCTUATION_RE = re.compile(r"[.!?…]\s*$")
_CONTINUATION_SIMILARITY_THRESHOLD = 0.5
_MAX_GROUP_LINES = 12


def group_into_chunks(text: str) -> list[str]:
    lines = split_blocks(text)
    if len(lines) <= 1:
        return lines

    embeddings = local_models.embed_texts(lines)

    groups: list[list[int]] = [[0]]
    for i in range(1, len(lines)):
        current_group = groups[-1]
        previous_index = current_group[-1]
        looks_incomplete = not _TERMINAL_PUNCTUATION_RE.search(lines[previous_index])
        similarity = float(embeddings[previous_index] @ embeddings[i])
        should_merge = len(current_group) < _MAX_GROUP_LINES and (
            looks_incomplete or similarity >= _CONTINUATION_SIMILARITY_THRESHOLD
        )
        if should_merge:
            current_group.append(i)
        else:
            groups.append([i])

    return [" ".join(lines[i] for i in group) for group in groups]
