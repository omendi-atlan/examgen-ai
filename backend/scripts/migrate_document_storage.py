"""Idempotently copy existing private local document objects to S3.

Run with DOCUMENT_STORAGE_BACKEND=s3 and the same DOCUMENT_STORAGE_PATH used by
the API. This utility never changes document IDs, versions, fingerprints,
provenance, or storage keys. Local copies are retained unless --delete-local
is explicitly supplied after a successful verified upload.
"""
import argparse
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import DocumentVersion
from app.services.object_storage import persist_file
from app.services.document_storage import resolve_storage_path


def migrate(*, delete_local: bool = False) -> tuple[int, int]:
    settings = get_settings()
    if settings.document_storage_backend != "s3":
        raise RuntimeError("Set DOCUMENT_STORAGE_BACKEND=s3 before running migration.")
    copied = 0
    skipped = 0
    with SessionLocal() as db:
        versions = db.scalars(select(DocumentVersion).order_by(DocumentVersion.created_at)).all()
        for version in versions:
            local_path = resolve_storage_path(Path(settings.document_storage_path), version.storage_key)
            if not local_path.is_file():
                raise FileNotFoundError(f"Local source object is missing for version {version.id}.")
            digest = hashlib.sha256()
            with local_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != version.sha256 or local_path.stat().st_size != version.size_bytes:
                raise ValueError(f"Local source integrity check failed for version {version.id}.")
            persist_file(local_path, version.storage_key)
            copied += 1
            if delete_local:
                local_path.unlink()
    return copied, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete local copies only after each S3 upload has passed size and SHA-256 verification.",
    )
    arguments = parser.parse_args()
    copied_count, skipped_count = migrate(delete_local=arguments.delete_local)
    print(f"Verified {copied_count} object(s); skipped {skipped_count}.")
