"""Local parsing only. Scanned pages require OCR capability or human review."""

from app.schemas import DomainError


def record_pdf(title, paragraphs):
    import io
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 18)]
    for text in paragraphs:
        story.extend([Paragraph(escape(str(text)), styles["BodyText"]), Spacer(1, 12)])
    SimpleDocTemplate(stream, pagesize=A4, title=title, author="Helm Broker").build(story)
    return stream.getvalue()


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
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise DomainError("Text documents must use UTF-8 encoding", 422)
        if not text.strip():
            raise DomainError("The document has no readable text", 422)
        return {"text": text, "pages": 1, "source": "uploaded-text"}
    raise DomainError("Supported document types are PDF and UTF-8 text", 422)
