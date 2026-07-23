"""Server-side revision diffing (section 7.3).

Built on ``difflib.SequenceMatcher`` rather than a third-party diff
library. Output is a plain list of dicts of *text* — no HTML is ever
built here, so callers rely on the template engine's normal
auto-escaping instead of any manual/`mark_safe` step. That is the
"mandatory HTML-escaping" the spec asks for: escaping happens exactly
once, in the template, and nothing in this module can bypass it.
"""

from __future__ import annotations

import difflib
import re

_TOKEN_RE = re.compile(r"(\s+)")


def _tokenize(line: str) -> list[str]:
    return [token for token in _TOKEN_RE.split(line) if token != ""]


def diff_words(old_line: str, new_line: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Word-level diff between two single lines.

    Returns ``(old_spans, new_spans)``, each a list of ``(text, tag)``
    with ``tag`` in {"equal", "removed", "added"} — used to highlight the
    specific changed fragment within an otherwise-similar line.
    """
    old_tokens = _tokenize(old_line)
    new_tokens = _tokenize(new_line)
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)

    old_spans: list[tuple[str, str]] = []
    new_spans: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_text = "".join(old_tokens[i1:i2])
        new_text = "".join(new_tokens[j1:j2])
        if tag == "equal":
            old_spans.append((old_text, "equal"))
            new_spans.append((new_text, "equal"))
        elif tag == "delete":
            old_spans.append((old_text, "removed"))
        elif tag == "insert":
            new_spans.append((new_text, "added"))
        elif tag == "replace":
            old_spans.append((old_text, "removed"))
            new_spans.append((new_text, "added"))
    return old_spans, new_spans


def build_line_diff(old_text: str, new_text: str) -> list[dict]:
    """Line-level diff between two full texts.

    Each entry has ``type`` in {"equal", "removed", "added", "changed"}
    and ``old``/``new`` line strings (``None`` where a side has nothing).
    "changed" entries additionally carry word-level spans so templates
    can highlight just the changed fragment within the line.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)

    entries: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                entries.append({"type": "equal", "old": line, "new": line})
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                entries.append({"type": "removed", "old": line, "new": None})
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                entries.append({"type": "added", "old": None, "new": line})
        elif tag == "replace":
            old_slice = old_lines[i1:i2]
            new_slice = new_lines[j1:j2]
            paired = max(len(old_slice), len(new_slice))
            for k in range(paired):
                old_line = old_slice[k] if k < len(old_slice) else None
                new_line = new_slice[k] if k < len(new_slice) else None
                if old_line is not None and new_line is not None:
                    old_spans, new_spans = diff_words(old_line, new_line)
                    entries.append(
                        {
                            "type": "changed",
                            "old": old_line,
                            "new": new_line,
                            "old_spans": old_spans,
                            "new_spans": new_spans,
                        }
                    )
                elif old_line is not None:
                    entries.append({"type": "removed", "old": old_line, "new": None})
                else:
                    entries.append({"type": "added", "old": None, "new": new_line})
    return entries
