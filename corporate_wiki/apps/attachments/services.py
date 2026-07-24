"""Document attachment upload pipeline — same storage discipline as
``apps.images``: everything lives inside SQLite as a ``BinaryField``,
nothing ever touches the filesystem/a media directory.

Only .txt/.docx/.pdf are accepted (the set of "text document" formats
this project supports). Each is opened with the library that would also
be used to read it back for the document-import feature, so a corrupt
or mislabeled upload is rejected at upload time rather than surfacing
as a confusing failure later.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import BinaryIO

from django.conf import settings
from docx import Document
from pypdf import PdfReader

from apps.accounts.models import User
from apps.attachments.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
    UnsupportedAttachmentFormatError,
)
from apps.attachments.models import ArticleAttachment
from apps.audit.services import record_event

ALLOWED_EXTENSIONS = {
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _read_all(file_obj: BinaryIO) -> bytes:
    file_obj.seek(0)
    return file_obj.read()


def _validate_content(extension: str, raw_bytes: bytes) -> None:
    if extension == "txt":
        try:
            raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidAttachmentError("Файл .txt должен быть в кодировке UTF-8.") from exc
    elif extension == "docx":
        try:
            Document(BytesIO(raw_bytes))
        except Exception as exc:
            raise InvalidAttachmentError("Файл повреждён или не является .docx.") from exc
    elif extension == "pdf":
        try:
            PdfReader(BytesIO(raw_bytes))
        except Exception as exc:
            raise InvalidAttachmentError("Файл повреждён или не является .pdf.") from exc


def upload_attachment(
    *,
    file_obj: BinaryIO,
    original_filename: str,
    uploaded_by: User,
    user_agent: str = "",
) -> ArticleAttachment:
    extension = _extension(original_filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedAttachmentFormatError("Поддерживаются только файлы .txt, .docx и .pdf.")

    raw_bytes = _read_all(file_obj)
    if not raw_bytes:
        raise InvalidAttachmentError("Файл пустой.")

    max_bytes = settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise AttachmentTooLargeError(f"Файл больше {settings.MAX_ATTACHMENT_SIZE_MB} МБ.")

    _validate_content(extension, raw_bytes)

    checksum = hashlib.sha256(raw_bytes).hexdigest()
    existing = ArticleAttachment.objects.filter(checksum=checksum).first()
    if existing is not None:
        return existing

    attachment = ArticleAttachment.objects.create(
        data=raw_bytes,
        original_filename=(original_filename or "")[:255],
        mime_type=ALLOWED_EXTENSIONS[extension],
        file_size=len(raw_bytes),
        uploaded_by=uploaded_by,
        checksum=checksum,
    )
    record_event(
        actor=uploaded_by,
        action="attachment.uploaded",
        object_type="attachment",
        object_id=attachment.pk,
        metadata={
            "original_filename": attachment.original_filename,
            "mime_type": attachment.mime_type,
        },
        user_agent=user_agent,
    )
    return attachment
