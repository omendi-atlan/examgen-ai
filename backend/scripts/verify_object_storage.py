"""Verify a configured S3-compatible bucket with a real upload/read/checksum/delete cycle.

Run only after configuring DOCUMENT_STORAGE_BACKEND=s3 and private bucket credentials
or workload identity. The script creates one short-lived object under a random key,
downloads it through the production storage adapter, verifies byte length and SHA-256,
and deletes the object in a finally block.
"""
import hashlib
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.services.object_storage import delete_file, open_storage_file, persist_file


def verify() -> None:
    settings = get_settings()
    if settings.document_storage_backend != "s3":
        raise RuntimeError("Set DOCUMENT_STORAGE_BACKEND=s3 before running this check.")
    if not settings.object_storage_bucket:
        raise RuntimeError("OBJECT_STORAGE_BUCKET is required.")

    payload = (
        b"EXAMGEN AI managed storage verification\n"
        b"This temporary object validates upload, private read, integrity and cleanup.\n"
    )
    digest = hashlib.sha256(payload).hexdigest()
    key = f"health-checks/{uuid4().hex}.txt"

    with tempfile.TemporaryDirectory(prefix="examgen-s3-smoke-") as directory:
        source = Path(directory) / "storage-smoke.txt"
        source.write_bytes(payload)
        uploaded = False
        try:
            persist_file(source, key)
            uploaded = True
            with open_storage_file(
                key,
                expected_size=len(payload),
                expected_sha256=digest,
            ) as downloaded:
                if downloaded.read_bytes() != payload:
                    raise RuntimeError("Managed storage returned content different from the source.")
        finally:
            if uploaded:
                delete_file(key)

    print(
        "S3-compatible storage smoke test passed: "
        f"bucket={settings.object_storage_bucket!r}, sha256={digest}, cleanup=verified"
    )


if __name__ == "__main__":
    verify()
