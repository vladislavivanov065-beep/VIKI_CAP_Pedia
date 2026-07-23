from io import BytesIO

from docx import Document
from pypdf import PdfWriter


def make_txt_bytes(text: str = "Пример текстового документа.") -> bytes:
    return text.encode("utf-8")


def make_docx_bytes(paragraphs: list[str] | None = None) -> bytes:
    document = Document()
    for text in paragraphs or ["Пример документа Word."]:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
