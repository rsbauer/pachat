from __future__ import annotations

import base64
import mimetypes
import subprocess
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import UUID

import xlrd
from docx import Document
from openpyxl import load_workbook
from PIL import Image, ImageOps
from pypdf import PdfReader
from striprtf.striprtf import rtf_to_text

from intake import TEXT_EXTENSIONS, get_user_document

MAX_DOCUMENT_CONTEXT_CHARS = 60_000
MAX_OFFICE_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_IMAGE_COUNT = 4
MAX_IMAGE_DIMENSION = 2048
MAX_IMAGE_BYTES = 20 * 1024 * 1024


def _check_office_archive(content: bytes, filename: str) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            expanded_size = sum(entry.file_size for entry in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{filename}: document is not a valid Office file") from exc
    if expanded_size > MAX_OFFICE_ARCHIVE_BYTES:
        raise ValueError(f"{filename}: expanded document is too large to analyze")


def _pdf_text(content: bytes, filename: str) -> str:
    try:
        reader = PdfReader(BytesIO(content), strict=False)
    except Exception as exc:
        raise ValueError(f"{filename}: PDF could not be opened") from exc
    if reader.is_encrypted:
        raise ValueError(f"{filename}: password-protected PDFs are not supported")
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
        if sum(map(len, pages)) > MAX_DOCUMENT_CONTEXT_CHARS:
            raise ValueError("Selected documents contain too much text to include in a single request")
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(f"{filename}: no selectable text found; scanned PDFs need OCR")
    return text


def _docx_text(content: bytes, filename: str) -> str:
    _check_office_archive(content, filename)
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise ValueError(f"{filename}: Word document could not be opened") from exc
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _doc_text(content: bytes, filename: str) -> str:
    try:
        result = subprocess.run(
            ["antiword", "-"],
            input=content,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise ValueError("Legacy .doc analysis is unavailable; the document parser is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{filename}: Word document took too long to analyze") from exc
    if result.returncode != 0:
        raise ValueError(f"{filename}: Word document could not be opened")
    return result.stdout.decode("utf-8", errors="replace")


def _xlsx_text(content: bytes, filename: str) -> str:
    _check_office_archive(content, filename)
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"{filename}: spreadsheet could not be opened") from exc
    parts = []
    try:
        for sheet in workbook.worksheets:
            parts.append(f"Sheet: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value) for value in row]
                parts.append("\t".join(values))
                if sum(map(len, parts)) > MAX_DOCUMENT_CONTEXT_CHARS:
                    raise ValueError("Selected documents contain too much text to include in a single request")
    finally:
        workbook.close()
    return "\n".join(parts)


def _xls_text(content: bytes, filename: str) -> str:
    try:
        workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
    except Exception as exc:
        raise ValueError(f"{filename}: spreadsheet could not be opened") from exc
    parts = []
    try:
        for sheet in workbook.sheets():
            parts.append(f"Sheet: {sheet.name}")
            for row_index in range(sheet.nrows):
                parts.append("\t".join(str(value) for value in sheet.row_values(row_index)))
                if sum(map(len, parts)) > MAX_DOCUMENT_CONTEXT_CHARS:
                    raise ValueError("Selected documents contain too much text to include in a single request")
    finally:
        workbook.release_resources()
    return "\n".join(parts)


def _image_data(content: bytes, filename: str) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened_image:
                opened_image.seek(0)
                image = ImageOps.exif_transpose(opened_image).convert("RGB")
                image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
                output = BytesIO()
                image.save(output, format="JPEG", quality=85, optimize=True)
    except Exception as exc:
        raise ValueError(f"{filename}: image could not be prepared for analysis") from exc
    image_bytes = output.getvalue()
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"{filename}: image is too large to include in a chat request")
    return base64.b64encode(image_bytes).decode("ascii")


def extract_document_text(filename: str, mime_type: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _pdf_text(content, filename)
    if suffix == ".docx":
        return _docx_text(content, filename)
    if suffix == ".doc":
        return _doc_text(content, filename)
    if suffix == ".xlsx":
        return _xlsx_text(content, filename)
    if suffix == ".xls":
        return _xls_text(content, filename)
    if suffix == ".rtf":
        try:
            return rtf_to_text(content.decode("utf-8", errors="replace"))
        except Exception as exc:
            raise ValueError(f"{filename}: RTF document could not be opened") from exc
    if suffix in TEXT_EXTENSIONS or mime_type.startswith("text/"):
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{filename}: text is not UTF-8 encoded") from exc
    if not mimetypes.guess_type(filename)[0]:
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    raise ValueError(f"{filename}: this file type cannot be added to chat context")


def build_document_context(
    user_id: UUID,
    document_ids: list[UUID],
    upload_dir: str,
    encryption_key: str,
) -> tuple[str, list[str]]:
    text_parts = []
    images = []
    image_filenames = []
    total_characters = 0
    filenames = []
    for document_id in dict.fromkeys(document_ids):
        document = get_user_document(user_id, document_id, upload_dir, encryption_key)
        if document is None:
            raise ValueError("A selected file is no longer available")
        filename = document["filename"]
        filenames.append(filename)
        if document["mime_type"].startswith("image/"):
            if len(images) >= MAX_IMAGE_COUNT:
                raise ValueError(f"Select no more than {MAX_IMAGE_COUNT} images for a conversation")
            images.append(_image_data(document["content"], filename))
            image_filenames.append(filename)
            continue

        text = extract_document_text(filename, document["mime_type"], document["content"]).strip()
        total_characters += len(text)
        if total_characters > MAX_DOCUMENT_CONTEXT_CHARS:
            raise ValueError("Selected documents contain too much text to include in a single request")
        if text:
            text_parts.append(f"File: {filename}\n{text}")

    if image_filenames:
        text_parts.append("Attached image files: " + ", ".join(image_filenames))
    return "\n\n".join(text_parts), images