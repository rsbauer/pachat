from __future__ import annotations

import mimetypes
import os
import socket
import struct
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken

from database import get_db_connection

MAX_UPLOAD_SIZE = 100 * 1024 * 1024
MAX_FILE_COUNT = 100
MAX_ARCHIVE_ITEMS = 100
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".png", ".tif", ".txt", ".rtf"}
TEXT_EXTENSIONS = {".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".xml", ".yaml", ".yml"}


class ScannerUnavailableError(Exception):
    pass


def is_acceptable_document(filename: str, content: bytes | None = None) -> bool:
    suffix = Path(filename).suffix.lower()
    if suffix in ALLOWED_EXTENSIONS or suffix in TEXT_EXTENSIONS:
        return True
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type and (mime_type.startswith("text/") or mime_type.startswith("image/")):
        return True
    if mime_type or content is None or b"\0" in content:
        return False
    try:
        content.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def scan_with_clamav(content: bytes, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=10) as scanner:
            scanner.settimeout(30)
            scanner.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 1024 * 1024):
                chunk = content[offset : offset + 1024 * 1024]
                scanner.sendall(struct.pack("!I", len(chunk)) + chunk)
            scanner.sendall(struct.pack("!I", 0))
            response = bytearray()
            while not response.endswith(b"\0"):
                part = scanner.recv(4096)
                if not part:
                    raise OSError("ClamAV closed the connection without a result")
                response.extend(part)
                if len(response) > 4096:
                    raise OSError("ClamAV returned an oversized response")
    except OSError as exc:
        raise ScannerUnavailableError("ClamAV could not scan the upload") from exc

    result = response.rstrip(b"\0").decode("utf-8", errors="replace")
    if result.endswith(": OK"):
        return True
    if result.endswith(" FOUND"):
        return False
    raise ScannerUnavailableError(f"Unexpected ClamAV response: {result}")


def decrypt_document(content: bytes, key: str) -> bytes:
    try:
        return Fernet(key.encode("ascii")).decrypt(content)
    except (ValueError, InvalidToken) as exc:
        raise ValueError("The configured encryption key cannot decrypt this document") from exc


def _document_entries(payloads: list[tuple[str, bytes]]) -> tuple[list[tuple[str, bytes]], list[dict[str, str]]]:
    documents = []
    rejected = []
    extracted_total = 0

    for filename, content in payloads:
        if Path(filename).suffix.lower() != ".zip":
            if is_acceptable_document(filename, content):
                documents.append((Path(filename).name, content))
            else:
                rejected.append({"filename": filename, "reason": "Unsupported file type"})
            continue

        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                items = [item for item in archive.infolist() if not item.is_dir()]
                if len(items) > MAX_ARCHIVE_ITEMS:
                    raise ValueError("ZIP archive contains too many files")
                for item in items:
                    name = PurePosixPath(item.filename).name
                    if not name or item.file_size > MAX_UPLOAD_SIZE:
                        rejected.append({"filename": item.filename, "reason": "File exceeds the upload size limit"})
                        continue
                    if item.external_attr >> 16 & 0o170000 == 0o120000:
                        rejected.append({"filename": item.filename, "reason": "Links are not accepted"})
                        continue
                    mime_type, _ = mimetypes.guess_type(name)
                    if not is_acceptable_document(name) and mime_type:
                        rejected.append({"filename": item.filename, "reason": "Unsupported file type"})
                        continue
                    extracted_total += item.file_size
                    if extracted_total > MAX_UPLOAD_SIZE:
                        raise ValueError("ZIP contents exceed the 100 MB upload limit")
                    with archive.open(item) as extracted:
                        document = extracted.read(MAX_UPLOAD_SIZE + 1)
                    if len(document) != item.file_size:
                        raise ValueError("ZIP entry size does not match its metadata")
                    if not is_acceptable_document(name, document):
                        rejected.append({"filename": item.filename, "reason": "Unsupported file type"})
                        continue
                    documents.append((name, document))
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
            raise ValueError(f"{filename}: invalid or unreadable ZIP archive") from exc

    return documents, rejected


def store_documents(
    payloads: list[tuple[str, bytes]],
    user_id: UUID,
    upload_dir: str,
    scanner_host: str,
    scanner_port: int,
    encryption_enabled: bool,
    encryption_key: str,
) -> dict:
    cipher = None
    if encryption_enabled and not encryption_key:
        raise ValueError("FILE_ENCRYPTION_KEY is required when file encryption is enabled")
    if encryption_enabled:
        try:
            cipher = Fernet(encryption_key.encode("ascii"))
        except (TypeError, ValueError) as exc:
            raise ValueError("FILE_ENCRYPTION_KEY must be a valid Fernet key") from exc

    documents, rejected = _document_entries(payloads)
    scanned = []
    for filename, content in documents:
        if scan_with_clamav(content, scanner_host, scanner_port):
            scanned.append((filename, content))
        else:
            rejected.append({"filename": filename, "reason": "Virus detected; file deleted"})

    if not scanned:
        return {"uploaded": [], "rejected": rejected}

    stored = []
    user_dir = Path(upload_dir) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(user_dir, 0o700)
    created_paths = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                for filename, content in scanned:
                    document_id = uuid4()
                    stored_name = f"{document_id}{Path(filename).suffix.lower()}"
                    stored_content = cipher.encrypt(content) if cipher else content
                    destination = user_dir / stored_name
                    descriptor = destination.open("xb")
                    created_paths.append(destination)
                    try:
                        os.chmod(destination, 0o600)
                        with descriptor:
                            descriptor.write(stored_content)
                    except Exception:
                        descriptor.close()
                        raise

                    mime_type = mimetypes.guess_type(filename)[0] or (
                        "text/plain" if Path(filename).suffix.lower() in TEXT_EXTENSIONS else "application/octet-stream"
                    )
                    cursor.execute(
                        """
                        INSERT INTO uploaded_documents
                            (id, user_id, original_name, stored_name, mime_type, size_bytes, is_encrypted)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (document_id, user_id, filename, stored_name, mime_type, len(content), encryption_enabled),
                    )
                    stored.append({"id": str(document_id), "filename": filename, "size_bytes": len(content)})
    except Exception:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise

    return {"uploaded": stored, "rejected": rejected}


def list_user_documents(user_id: UUID) -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, original_name, mime_type, size_bytes, created_at
                FROM uploaded_documents WHERE user_id = %s ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return [
        {"id": str(row[0]), "filename": row[1], "mime_type": row[2], "size_bytes": row[3], "created_at": row[4]}
        for row in rows
    ]


def get_user_document(user_id: UUID, document_id: UUID, upload_dir: str, encryption_key: str) -> dict | None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT original_name, stored_name, mime_type, is_encrypted
                FROM uploaded_documents WHERE id = %s AND user_id = %s
                """,
                (document_id, user_id),
            )
            row = cursor.fetchone()
    if row is None:
        return None

    filename, stored_name, mime_type, is_encrypted = row
    if Path(stored_name).name != stored_name:
        raise ValueError("Invalid stored document name")
    content = (Path(upload_dir) / str(user_id) / stored_name).read_bytes()
    if is_encrypted:
        content = decrypt_document(content, encryption_key)
    return {"filename": filename, "mime_type": mime_type, "content": content}


def delete_user_document(user_id: UUID, document_id: UUID, upload_dir: str) -> bool:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT stored_name FROM uploaded_documents WHERE id = %s AND user_id = %s",
                (document_id, user_id),
            )
            row = cursor.fetchone()
            if row is None:
                return False
            stored_name = row[0]
            cursor.execute(
                "DELETE FROM uploaded_documents WHERE id = %s AND user_id = %s",
                (document_id, user_id),
            )
    if Path(stored_name).name == stored_name:
        (Path(upload_dir) / str(user_id) / stored_name).unlink(missing_ok=True)
    return True