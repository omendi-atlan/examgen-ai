"""Private local and S3-compatible object storage adapters.

Object keys remain opaque and stable in PostgreSQL. Buckets must be private;
credentials are read only by the server-side API and worker processes.
"""
from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import get_settings


def _safe_key(key: str) -> str:
    candidate = Path(key)
    if candidate.is_absolute() or not key or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("Invalid document storage key.")
    if "\\" in key or key.startswith("/"):
        raise ValueError("Invalid document storage key.")
    return key


def _is_cloudflare_r2(endpoint_url: str | None) -> bool:
    """R2 encrypts objects at rest itself and rejects the AWS SSE request header."""
    hostname = urlparse(endpoint_url or "").hostname or ""
    return hostname == "r2.cloudflarestorage.com" or hostname.endswith(".r2.cloudflarestorage.com")


def _s3_client():
    settings = get_settings()
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - dependency is installed in API image
        raise RuntimeError("S3 storage requires the boto3 package.") from exc
    options: dict[str, object] = {"region_name": settings.object_storage_region}
    if settings.object_storage_endpoint_url:
        options["endpoint_url"] = settings.object_storage_endpoint_url
    access_key = settings.object_storage_access_key.get_secret_value() if settings.object_storage_access_key else ""
    secret_key = settings.object_storage_secret_key.get_secret_value() if settings.object_storage_secret_key else ""
    if access_key:
        options["aws_access_key_id"] = access_key
    if secret_key:
        options["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **options)


def persist_file(source: Path, storage_key: str) -> None:
    """Persist a validated, malware-scanned temporary file under its stable key."""
    key = _safe_key(storage_key)
    settings = get_settings()
    if settings.document_storage_backend == "local":
        root = Path(settings.document_storage_path).resolve()
        destination = (root / key).resolve()
        if root not in destination.parents:
            raise ValueError("Invalid document storage key.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
        return
    if not settings.object_storage_bucket:
        raise RuntimeError("OBJECT_STORAGE_BUCKET is required for S3 storage.")
    client = _s3_client()
    digest_state = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_state.update(chunk)
    digest = digest_state.hexdigest()
    extra_args: dict[str, object] = {"Metadata": {"sha256": digest}}
    # Cloudflare R2 automatically encrypts data at rest with AES-256 and its S3
    # API does not implement x-amz-server-side-encryption on PutObject.
    if not _is_cloudflare_r2(settings.object_storage_endpoint_url):
        extra_args["ServerSideEncryption"] = "AES256"
    client.upload_file(
        str(source),
        settings.object_storage_bucket,
        key,
        ExtraArgs=extra_args,
    )
    head = client.head_object(Bucket=settings.object_storage_bucket, Key=key)
    if head.get("ContentLength") != source.stat().st_size or head.get("Metadata", {}).get("sha256") != digest:
        client.delete_object(Bucket=settings.object_storage_bucket, Key=key)
        raise RuntimeError("Object storage verification failed after upload.")


@contextmanager
def open_storage_file(
    storage_key: str, *, expected_size: int | None = None, expected_sha256: str | None = None
) -> Iterator[Path]:
    """Yield a bounded local worker copy and always remove temporary downloads."""
    key = _safe_key(storage_key)
    settings = get_settings()
    if settings.document_storage_backend == "local":
        root = Path(settings.document_storage_path).resolve()
        path = (root / key).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("Stored academic source is unavailable.")
        _verify_file(path, expected_size, expected_sha256)
        yield path
        return
    if not settings.object_storage_bucket:
        raise RuntimeError("OBJECT_STORAGE_BUCKET is required for S3 storage.")
    client = _s3_client()
    metadata = client.head_object(Bucket=settings.object_storage_bucket, Key=key)
    remote_size = int(metadata.get("ContentLength", -1))
    if remote_size < 0 or remote_size > settings.max_document_upload_bytes:
        raise ValueError("Stored academic source exceeds the permitted size.")
    if expected_size is not None and remote_size != expected_size:
        raise ValueError("Stored academic source size does not match its database record.")
    with tempfile.TemporaryDirectory(prefix="examgen-object-") as directory:
        path = Path(directory) / Path(key).name
        client.download_file(settings.object_storage_bucket, key, str(path))
        _verify_file(path, expected_size, expected_sha256)
        yield path


def delete_file(storage_key: str) -> None:
    """Delete an object after a failed database transaction or duplicate rejection."""
    key = _safe_key(storage_key)
    settings = get_settings()
    if settings.document_storage_backend == "local":
        root = Path(settings.document_storage_path).resolve()
        path = (root / key).resolve()
        if root not in path.parents:
            raise ValueError("Invalid document storage key.")
        path.unlink(missing_ok=True)
        return
    if not settings.object_storage_bucket:
        raise RuntimeError("OBJECT_STORAGE_BUCKET is required for S3 storage.")
    _s3_client().delete_object(Bucket=settings.object_storage_bucket, Key=key)


def _verify_file(path: Path, expected_size: int | None, expected_sha256: str | None) -> None:
    """Verify a stored object against immutable database metadata before parsing."""
    if expected_size is not None and path.stat().st_size != expected_size:
        raise ValueError("Stored academic source size does not match its database record.")
    if expected_sha256 is not None:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ValueError("Stored academic source checksum does not match its database record.")
