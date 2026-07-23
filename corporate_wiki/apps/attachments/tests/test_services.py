from io import BytesIO

import pytest
from django.test import override_settings

from apps.accounts.factories import UserFactory
from apps.attachments import services
from apps.attachments.exceptions import (
    AttachmentTooLargeError,
    InvalidAttachmentError,
    UnsupportedAttachmentFormatError,
)
from apps.attachments.models import ArticleAttachment
from apps.attachments.tests.factories import make_docx_bytes, make_pdf_bytes, make_txt_bytes

pytestmark = pytest.mark.django_db


def _upload(data: bytes, *, filename: str, uploaded_by=None):
    if uploaded_by is None:
        uploaded_by = UserFactory()
    return services.upload_attachment(
        file_obj=BytesIO(data), original_filename=filename, uploaded_by=uploaded_by
    )


def test_upload_accepts_txt_docx_pdf():
    txt = _upload(make_txt_bytes(), filename="notes.txt")
    docx = _upload(make_docx_bytes(), filename="report.docx")
    pdf = _upload(make_pdf_bytes(), filename="scan.pdf")

    assert txt.mime_type == "text/plain"
    assert docx.mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert pdf.mime_type == "application/pdf"


def test_upload_rejects_unsupported_extension():
    with pytest.raises(UnsupportedAttachmentFormatError):
        _upload(b"not really a document", filename="virus.exe")


def test_upload_rejects_empty_file():
    with pytest.raises(InvalidAttachmentError):
        _upload(b"", filename="empty.txt")


def test_upload_rejects_non_utf8_txt():
    with pytest.raises(InvalidAttachmentError):
        _upload("Привет".encode("cp1251"), filename="broken.txt")


def test_upload_rejects_corrupted_docx():
    with pytest.raises(InvalidAttachmentError):
        _upload(b"this is not a real docx file", filename="fake.docx")


def test_upload_rejects_corrupted_pdf():
    with pytest.raises(InvalidAttachmentError):
        _upload(b"this is not a real pdf file", filename="fake.pdf")


@override_settings(MAX_ATTACHMENT_SIZE_MB=0)
def test_upload_rejects_oversized_file():
    with pytest.raises(AttachmentTooLargeError):
        _upload(make_txt_bytes("x" * 1000), filename="big.txt")


def test_reuploading_identical_bytes_returns_existing_row():
    data = make_txt_bytes()
    user = UserFactory()

    first = _upload(data, filename="a.txt", uploaded_by=user)
    second = _upload(data, filename="a-copy.txt", uploaded_by=user)

    assert first.pk == second.pk
    assert ArticleAttachment.objects.count() == 1
