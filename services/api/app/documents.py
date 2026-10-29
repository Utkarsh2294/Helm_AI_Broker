"""Local parsing only. Scanned pages require OCR capability or human review."""

from app.schemas import DomainError


def extract_document(raw: bytes, mime: str):
    if len(raw) > 10_000_000:
        raise DomainError("Document exceeds the 10 MB limit", 413)
    if mime == "application/pdf":
        import pymupdf

        try:
            with pymupdf.open(stream=raw, filetype="pdf") as document:
                if len(document) > 50:
                    raise DomainError("Document exceeds the 50-page limit", 422)
                text = "\n".join(page.get_text() for page in document)
                if not text.strip():
                    raise DomainError("H8: scanned document needs OCR or human transcription", 422)
                return {"text": text, "pages": len(document), "source": "uploaded-pdf"}
        except DomainError:
            raise
        except Exception:
            raise DomainError("Unreadable PDF document", 422)
    if mime == "text/plain":
        return {"text": raw.decode("utf-8", errors="strict"), "pages": 1, "source": "uploaded-text"}
    raise DomainError("Supported document types are PDF and UTF-8 text", 422)
