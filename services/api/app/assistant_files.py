"""Bounded local extraction. Uploaded prose is data, never assistant instructions."""

import csv
import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from app.schemas import DomainError

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT = 60_000
ACCEPTED = {"pdf", "docx", "xlsx", "csv", "png", "jpg", "jpeg", "webp", "txt"}


def ocr(raw, extension):
    executable = shutil.which("tesseract")
    if not executable:
        raise DomainError(
            "Local OCR is unavailable. Upload a text PDF, DOCX or CSV, or ask the operator to install Tesseract with English data.",
            422,
        )
    with tempfile.TemporaryDirectory(prefix="helm-ocr-") as directory:
        path = Path(directory) / ("input." + extension)
        path.write_bytes(raw)
        try:
            result = subprocess.run(
                [executable, str(path), "stdout", "-l", "eng"], capture_output=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            raise DomainError("OCR timed out; upload fewer pages or a text document", 422)
        if result.returncode:
            raise DomainError("The image could not be read by local OCR", 422)
        return result.stdout.decode("utf-8", errors="replace")[:MAX_TEXT]


def parse_file(raw, filename):
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ACCEPTED:
        raise DomainError("Supported: PDF, DOCX, XLSX, CSV, PNG, JPG, WebP and UTF-8 text", 422)
    if not raw or len(raw) > MAX_BYTES:
        raise DomainError("Upload a non-empty file of at most 20 MB", 413)
    method = "local_text"
    try:
        if extension == "pdf":
            import pymupdf

            with pymupdf.open(stream=raw, filetype="pdf") as document:
                if document.is_encrypted or len(document) > 50:
                    raise DomainError("Use an unlocked PDF of at most 50 pages", 422)
                parts = []
                for page in document:
                    text = page.get_text()
                    if not text.strip():
                        if len(document) > 5:
                            raise DomainError(
                                "Scanned PDFs are limited to five pages; upload a text PDF for larger files",
                                422,
                            )
                        text = ocr(page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes("png"), "png")
                        method = "local_ocr"
                    parts.append(text[:MAX_TEXT])
                text = "\n".join(parts)
        elif extension in {"docx", "xlsx"}:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > 40 * 1024 * 1024:
                    raise DomainError("The expanded Office document is too large", 413)
                if extension == "docx":
                    root = ET.fromstring(archive.read("word/document.xml"))
                    text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
                else:
                    shared = []
                    if "xl/sharedStrings.xml" in archive.namelist():
                        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                        shared = ["".join(node.itertext()) for node in root]
                    parts = []
                    for name in sorted(archive.namelist()):
                        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                            sheet = ET.fromstring(archive.read(name))
                            for row in (n for n in sheet.iter() if n.tag.endswith("}row")):
                                values = []
                                for cell in row:
                                    value = "".join(cell.itertext())
                                    values.append(shared[int(value)] if cell.get("t") == "s" else value)
                                parts.append(" | ".join(values))
                                if len(parts) >= 200:
                                    break
                            if len(parts) >= 200:
                                break
                    text = "\n".join(parts)
                    method = "local_rows_sample_200"
        elif extension in {"csv", "txt"}:
            text = raw.decode("utf-8-sig", errors="strict")
            if extension == "csv":
                csv.field_size_limit(MAX_TEXT)
                rows = csv.reader(io.StringIO(text))
                text = "\n".join(" | ".join(row) for _, row in zip(range(200), rows))
                method = "local_rows_sample_200"
        else:
            text = ocr(raw, extension)
            method = "local_ocr"
    except DomainError:
        raise
    except Exception:
        raise DomainError("Unreadable file. Check the format and upload an unlocked, valid document", 422)
    if not text.strip():
        raise DomainError("No readable text was found in this file", 422)
    return {"text": text[:MAX_TEXT], "method": method, "truncated": len(text) > MAX_TEXT}
