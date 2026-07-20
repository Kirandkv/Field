"""Text extraction: .txt/.md native, .pdf native-text via pypdf.

OCR fallback for scanned/image-only PDFs is planned (M2, requires Tesseract) — see
docs/ROADMAP.md. When a PDF page yields no extractable text today, that page is emitted
with empty text and ocr_confidence=0.0 rather than silently dropped, so downstream code
can see the gap instead of guessing why retrieval found nothing.
"""

from __future__ import annotations

import io

from fieldforge_contracts import DocumentPage

SUPPORTED_CONTENT_TYPES = {"text/plain", "text/markdown", "application/pdf"}


class UnsupportedContentType(ValueError):
    pass


def extract_pages(document_id: str, content_type: str, raw_bytes: bytes) -> list[DocumentPage]:
    if content_type in ("text/plain", "text/markdown"):
        return _extract_text(document_id, raw_bytes)
    if content_type == "application/pdf":
        return _extract_pdf(document_id, raw_bytes)
    raise UnsupportedContentType(
        f"content_type={content_type!r} not supported; supported={sorted(SUPPORTED_CONTENT_TYPES)}"
    )


def _extract_text(document_id: str, raw_bytes: bytes) -> list[DocumentPage]:
    text = raw_bytes.decode("utf-8", errors="replace")
    # Normalize CRLF/CR to LF so downstream chunk offsets and citation quotes never
    # carry stray \r characters — found via a live upload of a Windows-authored file
    # during verification (curl preserved the file's raw CRLF bytes).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [DocumentPage(document_id=document_id, page_number=1, text=text, ocr_confidence=None)]


def _extract_pdf(document_id: str, raw_bytes: bytes) -> list[DocumentPage]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes))
    pages: list[DocumentPage] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        confidence = None if text.strip() else 0.0
        pages.append(
            DocumentPage(
                document_id=document_id, page_number=i, text=text, ocr_confidence=confidence
            )
        )
    return pages
