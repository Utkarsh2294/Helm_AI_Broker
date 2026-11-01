"""Bounded local extraction. Uploaded prose is data, never assistant instructions."""

import csv
import json
import io
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from app.schemas import DomainError

MAX_BYTES = 25 * 1024 * 1024
MAX_TEXT = 50_000
MAX_COMBINED_TEXT = 150_000
AUDIO = {"mp3", "wav", "m4a", "webm"}
ACCEPTED = {
    "pdf",
    "docx",
    "xlsx",
    "xls",
    "csv",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "tif",
    "tiff",
    "txt",
    "md",
    "json",
} | AUDIO


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
        raise DomainError(
            "Supported: PDF, Word, Excel, CSV, images/TIFF, UTF-8 text/Markdown/JSON and MP3/WAV/M4A/WebM audio",
            422,
        )
    if not raw or len(raw) > MAX_BYTES:
        raise DomainError("Upload a non-empty file of at most 25 MB", 413)
    method = "local_text"
    pages = None
    limited = False
    try:
        if extension == "pdf":
            import pymupdf

            with pymupdf.open(stream=raw, filetype="pdf") as document:
                pages = len(document)
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
                    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                    text = "\n".join(
                        "".join(node.text or "" for node in paragraph.iter(namespace + "t"))
                        for paragraph in root.iter(namespace + "p")
                    )
                else:
                    shared = []
                    if "xl/sharedStrings.xml" in archive.namelist():
                        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                        shared = ["".join(node.itertext()) for node in root]
                    parts = []
                    length = 0
                    for name in sorted(archive.namelist()):
                        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                            sheet = ET.fromstring(archive.read(name))
                            for row in (n for n in sheet.iter() if n.tag.endswith("}row")):
                                values = []
                                for cell in row:
                                    value = "".join(cell.itertext())
                                    values.append(shared[int(value)] if cell.get("t") == "s" else value)
                                line = " | ".join(values)
                                parts.append(line)
                                length += len(line)
                                if length >= MAX_TEXT:
                                    limited = True
                                    break
                            if limited:
                                break
                    text = "\n".join(parts)
                    method = "local_sheet_text"
        elif extension == "xls":
            import xlrd

            with xlrd.open_workbook(file_contents=raw, on_demand=True) as workbook:
                parts = []
                length = 0
                for sheet in workbook.sheets():
                    for row in sheet.get_rows():
                        line = " | ".join(str(cell.value) for cell in row)
                        parts.append(line)
                        length += len(line)
                        if length >= MAX_TEXT:
                            limited = True
                            break
                    if limited:
                        break
                text = "\n".join(parts)
                method = "local_sheet_text"
        elif extension in {"csv", "txt", "md", "json"}:
            text = raw.decode("utf-8-sig", errors="strict")
            if extension == "json":
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            if extension == "csv":
                csv.field_size_limit(MAX_TEXT)
                rows = csv.reader(io.StringIO(text))
                parts = []
                length = 0
                for row in rows:
                    line = " | ".join(row)
                    parts.append(line)
                    length += len(line)
                    if length >= MAX_TEXT:
                        limited = True
                        break
                text = "\n".join(parts)
                method = "local_csv_text"
        elif extension in AUDIO:
            from app.speech import transcribe

            transcript = transcribe(raw, max_seconds=600)
            text, method = transcript["text"], transcript["method"]
        else:
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as image:
                pages = getattr(image, "n_frames", 1)
                if pages > 5 or image.width * image.height > 20_000_000:
                    raise DomainError("OCR images are limited to five pages and 20 megapixels per page", 422)
            text = ocr(raw, extension)
            method = "local_ocr"
    except DomainError:
        raise
    except Exception:
        raise DomainError("Unreadable file. Check the format and upload an unlocked, valid document", 422)
    if not text.strip():
        raise DomainError("No readable text was found in this file", 422)
    return {
        "text": text[:MAX_TEXT],
        "method": method,
        "truncated": limited or len(text) > MAX_TEXT,
        "pages": pages,
        "characters": min(len(text), MAX_TEXT),
    }
