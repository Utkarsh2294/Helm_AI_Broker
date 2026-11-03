"""Watermarked demo exports with measured IPID pagination; facts are never trimmed."""

import io
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from app.buying_templates import WATERMARK
from app.schemas import DomainError


def build_pdf(content, kind):
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize, styles["BodyText"].leading = 10, 14
    story = [
        Paragraph(escape(content["title"]), styles["Title"]),
        Paragraph(
            "Fictional demonstration. Not an offer, insurer approval or live policy.", styles["BodyText"]
        ),
        Spacer(1, 14),
    ]
    for index, section in enumerate(content.get("sections", [])):
        if kind == "ipid" and index == 5:
            story.append(PageBreak())
        story.extend(
            [
                Paragraph(escape(section["heading"]), styles["Heading3"]),
                Paragraph(escape(section["text"]).replace("\n", "<br/>"), styles["BodyText"]),
                Spacer(1, 8),
            ]
        )

    def footer(canvas, document):
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColorRGB(0.35, 0.35, 0.35)
        canvas.drawCentredString(A4[0] / 2, 27, WATERMARK)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 36, 14, f"Page {document.page}")

    SimpleDocTemplate(
        stream, pagesize=A4, topMargin=36, bottomMargin=48, leftMargin=40, rightMargin=40
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    raw = stream.getvalue()
    if kind == "ipid":
        import pymupdf

        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            if len(pdf) > 3:
                raise DomainError(
                    "The IPID exceeds three pages. Shorten explanatory text without removing factual content",
                    422,
                )
    return raw
