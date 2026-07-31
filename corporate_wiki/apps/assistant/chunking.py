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

Punctuation alone is not a reliable "this line is finished" signal -- a
lot of real text (addresses, labels, informal notes) never uses
./!/?/: at all, so a missing terminal mark can't be trusted on its own to
mean "still the same thought". A line is folded into the fragment being
built only when the embeddings say it's actually related:
  - similarity >= _CONTINUATION_SIMILARITY_THRESHOLD merges regardless of
    punctuation -- prose that continues the same idea across a line
    break without an obvious punctuation tell, or
  - similarity >= _UNPUNCTUATED_SIMILARITY_FLOOR (a much lower bar) merges
    *only* when the fragment's last line has no sentence-ending
    punctuation -- a missing "." is still a hint the line is a
    label/intro rather than a complete thought on its own ("биллинг
    адрес", "Случаи, при которых возможен овердрафт." with a trailing
    ":", a heading), but it's a weak one, so this still refuses to merge
    two lines that just happen to both lack a period while actually being
    about different things (see
    test_group_into_chunks_never_merges_unrelated_unpunctuated_lines).
Capped by _MAX_GROUP_LINES so a long run of related unpunctuated lines
can't merge into one unbounded blob.
"""

from __future__ import annotations

import re

from apps.assistant import local_models
from apps.assistant.text_utils import split_blocks

_TERMINAL_PUNCTUATION_RE = re.compile(r"[.!?…]\s*$")
_CONTINUATION_SIMILARITY_THRESHOLD = 0.5
# Same cutoff apps.assistant.retrieval uses for "too dissimilar to be
# relevant" -- reused here as the floor below which two lines are treated
# as unrelated even when neither ends in punctuation.
_UNPUNCTUATED_SIMILARITY_FLOOR = 0.2
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
        required_similarity = (
            _UNPUNCTUATED_SIMILARITY_FLOOR
            if looks_incomplete
            else _CONTINUATION_SIMILARITY_THRESHOLD
        )
        should_merge = len(current_group) < _MAX_GROUP_LINES and similarity >= required_similarity
        if should_merge:
            current_group.append(i)
        else:
            groups.append([i])

    # Joined with a line break, not a space, so a multi-line block like an
    # address still reads as one when it comes back as an answer (the
    # answer element has white-space: pre-wrap, see style.css).
    return ["\n".join(lines[i] for i in group) for group in groups]
