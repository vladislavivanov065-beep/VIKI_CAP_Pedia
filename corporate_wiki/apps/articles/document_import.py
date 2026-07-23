"""Admin document-import wizard: split an uploaded document into article
drafts by heading, for the administrator to review one by one.

Heading detection is a deterministic heuristic (Markdown ``#`` syntax, .docx
paragraph styles, or simple plain-text patterns) — there is no AI/LLM
involved, so a split can be imperfect. That is an accepted trade-off: the
administrator reviews and can edit every proposed block before it becomes a
real article.
"""

from __future__ import annotations

import dataclasses
import re
from io import BytesIO
from typing import BinaryIO

from django.conf import settings
from docx import Document
from pypdf import PdfReader

from apps.attachments.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
    UnsupportedAttachmentFormatError,
)

SUPPORTED_EXTENSIONS = {"txt", "docx", "pdf"}

_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_NUMBERED_HEADING_RE = re.compile(r"^(?:\d+[.\)]){1,3}\s*(?=\S)")
_CHAPTER_WORD_RE = re.compile(r"^(глава|раздел|часть|section|chapter)\b", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.,;:]\s*$")
_DOCX_HEADING_STYLE_RE = re.compile(r"^heading\s*\d?$", re.IGNORECASE)
_MAX_HEADING_LENGTH = 120


@dataclasses.dataclass
class DocumentBlock:
    title: str
    content: str


@dataclasses.dataclass
class _Line:
    text: str
    is_heading: bool


def extension_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def parse_uploaded_document(*, file_obj: BinaryIO, original_filename: str) -> list[DocumentBlock]:
    """Validate an uploaded document and split it into proposed article blocks."""
    extension = extension_of(original_filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedAttachmentFormatError("Поддерживаются только файлы .txt, .docx и .pdf.")

    file_obj.seek(0)
    raw_bytes = file_obj.read()
    if not raw_bytes:
        raise InvalidAttachmentError("Файл пустой.")

    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise AttachmentTooLargeError(f"Файл больше {settings.MAX_ATTACHMENT_SIZE_MB} МБ.")

    fallback_title = original_filename.rsplit(".", 1)[0].strip() or "Импортированный документ"
    return split_document_into_blocks(
        file_bytes=raw_bytes, extension=extension, fallback_title=fallback_title
    )


def split_document_into_blocks(
    *, file_bytes: bytes, extension: str, fallback_title: str
) -> list[DocumentBlock]:
    if extension == "txt":
        lines = _lines_from_txt(file_bytes)
    elif extension == "docx":
        lines = _lines_from_docx(file_bytes)
    elif extension == "pdf":
        lines = _lines_from_pdf(file_bytes)
    else:
        raise UnsupportedAttachmentFormatError(f"Неподдерживаемый формат файла: .{extension}")

    return _group_lines_into_blocks(lines, fallback_title=fallback_title)


def _lines_from_txt(file_bytes: bytes) -> list[_Line]:
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidAttachmentError("Файл .txt должен быть в кодировке UTF-8.") from exc
    return [_classify_plain_line(line) for line in text.splitlines() if line.strip()]


def _lines_from_docx(file_bytes: bytes) -> list[_Line]:
    try:
        document = Document(BytesIO(file_bytes))
    except Exception as exc:
        raise InvalidAttachmentError("Файл повреждён или не является .docx.") from exc

    lines: list[_Line] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style else ""
        is_heading = bool(_DOCX_HEADING_STYLE_RE.match(style_name or ""))
        lines.append(_Line(text=text, is_heading=is_heading))
    return lines


def _lines_from_pdf(file_bytes: bytes) -> list[_Line]:
    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise InvalidAttachmentError("Файл повреждён или не является .pdf.") from exc

    lines: list[_Line] = []
    for page_text in pages_text:
        for line in page_text.splitlines():
            if line.strip():
                lines.append(_classify_plain_line(line))
    return lines


def _classify_plain_line(line: str) -> _Line:
    stripped = line.strip()
    markdown_match = _MARKDOWN_HEADING_RE.match(stripped)
    if markdown_match:
        return _Line(text=markdown_match.group(1).strip(), is_heading=True)

    is_heading = (
        len(stripped) <= _MAX_HEADING_LENGTH
        and not _SENTENCE_END_RE.search(stripped)
        and (
            _NUMBERED_HEADING_RE.match(stripped) is not None
            or _CHAPTER_WORD_RE.match(stripped) is not None
            or (stripped.isupper() and 1 <= len(stripped.split()) <= 12)
        )
    )
    return _Line(text=stripped, is_heading=is_heading)


def _group_lines_into_blocks(lines: list[_Line], *, fallback_title: str) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    current_title: str | None = None
    current_paragraphs: list[str] = []

    def flush() -> None:
        content = "\n\n".join(current_paragraphs).strip()
        title = _clean_title(current_title) if current_title else fallback_title
        if not content and not current_title:
            return
        blocks.append(DocumentBlock(title=title, content=content))

    for line in lines:
        if line.is_heading:
            if current_title is not None or current_paragraphs:
                flush()
            current_title = line.text
            current_paragraphs = []
        else:
            current_paragraphs.append(line.text)

    if current_title is not None or current_paragraphs:
        flush()

    if not blocks:
        blocks.append(DocumentBlock(title=fallback_title, content=""))

    return blocks


def _clean_title(title: str) -> str:
    if _NUMBERED_HEADING_RE.match(title):
        title = _NUMBERED_HEADING_RE.sub("", title, count=1).strip()
    title = title[:200].strip()
    return title or "Без названия"
