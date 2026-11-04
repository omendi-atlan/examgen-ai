"""Private local storage with strict upload validation and immutable object keys."""

import hashlib
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.services.malware_scanning import MalwareDetectedError, scan_file\nfrom app.services.object_storage import persist_file

SUPPORTED_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".md": "text/markdown",
}
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 5000


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    original_filename: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    malware_scan: dict[str, str | bool]


def _validate_package(path: Path, extension: str, max_compression_ratio: int) -> None:
    """Reject malformed, encrypted, oversized or mismatched Office packages."""
    expected = {
        ".docx": "word/document.xml",
        ".pptx": "ppt/presentation.xml",
    }[extension]
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("Office package contains too many entries.")
            if sum(item.file_size for item in entries) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError("Office package expands beyond the permitted size.")
            if any(item.flag_bits & 0x1 for item in entries):
                raise ValueError("Encrypted Office packages are not accepted.")
            if any(
                (item.file_size > 0 and item.compress_size == 0)
                or (item.compress_size > 0 and item.file_size / item.compress_size > max_compression_ratio)
                for item in entries
            ):
                raise ValueError("Office package compression ratio exceeds the permitted limit.")
            if any(((item.external_attr >> 16) & 0o170000) == 0o120000 for item in entries):
                raise ValueError("Office packages containing symbolic links are not accepted.")
            if expected not in archive.namelist():
                raise ValueError("Office package does not match its declared file type.")
            if "[Content_Types].xml" not in archive.namelist():
                raise ValueError("Invalid Office package structure.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("Invalid Office document package.") from exc


async def store_upload(
    upload: UploadFile,
    storage_root: Path,
    max_bytes: int,
) -> StoredUpload:
    """Stream, hash, validate and atomically store an upload under a generated key."""
    raw_name = (upload.filename or "").replace("\\", "/").split("/")[-1].strip()
    if not raw_name or len(raw_name) > 255:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    extension = Path(raw_name).suffix.lower()
    if extension not in SUPPORTED_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported academic document format.")

    storage_root.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    digest = hashlib.sha256()
    size = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".upload-", suffix=".part", dir=storage_root, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Upload exceeds the configured size limit.",
                    )
                digest.update(chunk)
                temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())

        if size == 0:
            raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")
        with temporary_path.open("rb") as source:
            signature = source.read(8)
        if extension == ".pdf" and not signature.startswith(b"%PDF-"):
            raise HTTPException(status_code=415, detail="File content is not a valid PDF.")
        if extension in {".docx", ".pptx"}:
            if not signature.startswith(b"PK"):
                raise HTTPException(status_code=415, detail="File content is not a valid Office package.")
            try:
                from app.core.config import get_settings

                _validate_package(temporary_path, extension, get_settings().max_office_archive_ratio)
            except ValueError as exc:
                raise HTTPException(status_code=415, detail=str(exc)) from exc
        if extension in {".txt", ".md"}:
            try:
                temporary_path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=415, detail="Text files must use UTF-8 encoding.") from exc

        try:
            malware_scan = scan_file(temporary_path)
        except MalwareDetectedError as exc:
            raise HTTPException(status_code=422, detail="Upload rejected: malicious content detected.") from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Malware scanning is unavailable; upload rejected.",
            ) from exc

        object_id = uuid4().hex
        storage_key = f"{object_id[:2]}/{object_id}{extension}"
        destination = storage_root / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary_path, destination)
        temporary_path = None
        return StoredUpload(
            storage_key=storage_key,
            original_filename=raw_name,
            extension=extension,
            media_type=SUPPORTED_TYPES[extension],
            size_bytes=size,
            sha256=digest.hexdigest(),
            malware_scan=malware_scan,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await upload.close()


def resolve_storage_path(storage_root: Path, storage_key: str) -> Path:
    """Resolve only generated relative object keys contained by the storage root."""
    root = storage_root.resolve()
    path = (root / storage_key).resolve()
    if root not in path.parents:
        raise ValueError("Invalid document storage key.")
    return path
