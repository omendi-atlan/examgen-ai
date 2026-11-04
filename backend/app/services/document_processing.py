"""Durable database-backed document processing worker and extraction quality checks."""

import logging
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import (
    DocumentExtraction,
    DocumentProcessingJob,
    DocumentTextSegment,
    DocumentVersion,
    ExtractionJobStatus,
    ExtractionStatus,
)
from app.services.document_extraction import extract_document
from app.services.document_storage import resolve_storage_path

logger = logging.getLogger(__name__)
MIN_REVIEW_CHARACTERS_PER_PAGE = 40


def extraction_quality(
    *, character_count: int, page_count: int | None, segment_count: int, status: str
) -> dict[str, object]:
    """Return transparent heuristics; never silently approve low-quality extraction."""
    if status == ExtractionStatus.FAILED.value:
        outcome = "failed"
        reasons = ["Extraction failed; inspect the source and retry."]
    elif status == ExtractionStatus.NEEDS_OCR.value:
        outcome = "needs_ocr"
        reasons = ["No selectable text was found; OCR is required."]
    elif character_count == 0 or segment_count == 0:
        outcome = "needs_review"
        reasons = ["No text segments were extracted."]
    elif page_count and character_count / page_count < MIN_REVIEW_CHARACTERS_PER_PAGE:
        outcome = "needs_review"
        reasons = ["Extracted text density is unusually low for the page count."]
    else:
        outcome = "ready_for_review"
        reasons = []
    return {
        "outcome": outcome,
        "character_count": character_count,
        "segment_count": segment_count,
        "page_count": page_count,
        "reasons": reasons,
        "automatically_approved": False,
    }


def process_job(db: Session, job_id: UUID) -> bool:
    """Process one already-claimed job. All results remain linked to the immutable version."""
    job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.id == job_id)
        .options(
            selectinload(DocumentProcessingJob.version).selectinload(DocumentVersion.extraction)
        )
    )
    if job is None or job.status != ExtractionJobStatus.PROCESSING:
        return False

    version = job.version
    extraction = version.extraction
    if extraction is None:
        extraction = DocumentExtraction(
            version_id=version.id,
            status=ExtractionStatus.PROCESSING,
            parser_name="pending",
            parser_version="0",
            character_count=0,
            extraction_metadata={},
        )
        db.add(extraction)
        db.flush()

    source_path = resolve_storage_path(
        Path(get_settings().document_storage_path), version.storage_key
    )
    try:
        result = extract_document(source_path, version.file_extension, enable_ocr=True)
        extraction.parser_name = result.parser_name
        extraction.parser_version = result.parser_version
        extraction.page_count = result.page_count
        extraction.character_count = sum(len(segment.text) for segment in result.segments)
        extraction.extraction_metadata = {
            **result.metadata,
            "ocr": result.metadata.get("ocr", {"performed": False}),
        }
        extraction.error_message = None
        extraction.quality_report = extraction_quality(
            character_count=extraction.character_count,
            page_count=extraction.page_count,
            segment_count=len(result.segments),
            status=(
                ExtractionStatus.NEEDS_OCR.value
                if result.needs_ocr
                else ExtractionStatus.EXTRACTED.value
                if result.segments
                else ExtractionStatus.EMPTY.value
            ),
        )
        extraction.status = (
            ExtractionStatus.NEEDS_OCR
            if result.needs_ocr
            else ExtractionStatus.EXTRACTED
            if result.segments
            else ExtractionStatus.EMPTY
        )
        db.add_all(
            [
                DocumentTextSegment(
                    extraction_id=extraction.id,
                    ordinal=index,
                    locator=segment.locator,
                    text=segment.text,
                    metadata_json=segment.metadata,
                )
                for index, segment in enumerate(result.segments, start=1)
            ]
        )
        job.status = ExtractionJobStatus.COMPLETED
        job.error_message = None
        job.finished_at = time.time()
        db.commit()
        return True
    except Exception as exc:
        logger.exception("Document processing failed for version %s", version.id)
        job.attempts += 1
        job.error_message = f"Processing failed ({type(exc).__name__})."
        extraction.status = ExtractionStatus.FAILED
        extraction.error_message = job.error_message
        if job.attempts < job.max_attempts:
            job.status = ExtractionJobStatus.QUEUED
        else:
            job.status = ExtractionJobStatus.FAILED
            job.finished_at = time.time()
        db.commit()
        return False


def claim_next_job(db: Session) -> UUID | None:
    """Claim one queued job using row locking on PostgreSQL."""
    statement = (
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.status == ExtractionJobStatus.QUEUED)
        .order_by(DocumentProcessingJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalar(statement)
    if job is None:
        return None
    job.status = ExtractionJobStatus.PROCESSING
    job.started_at = time.time()
    db.commit()
    return job.id


def run_once() -> bool:
    """Claim and process one queued job; suitable for a dedicated worker process."""
    with SessionLocal() as db:
        job_id = claim_next_job(db)
        if job_id is None:
            return False
        process_job(db, job_id)
        return True


def run_worker(poll_seconds: float = 2.0) -> None:
    """Continuously consume the durable database queue."""
    while True:
        if not run_once():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
