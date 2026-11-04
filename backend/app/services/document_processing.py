"""Crash-recoverable database-backed document worker and extraction quality checks."""

import logging
import time
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import (
    DocumentExtraction,
    DocumentProcessingJob,
    DocumentTextSegment,
    ExtractionJobStatus,
    ExtractionStatus,
)
from app.services.document_extraction import extract_document
from app.services.object_storage import open_storage_file

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


def recover_expired_jobs(db: Session, *, now: float | None = None) -> int:
    """Requeue expired worker leases, or fail jobs that exhausted their attempts."""
    current_time = now if now is not None else time.time()
    expired = db.scalars(
        select(DocumentProcessingJob)
        .where(
            DocumentProcessingJob.status == ExtractionJobStatus.PROCESSING,
            DocumentProcessingJob.lease_expires_at.is_not(None),
            DocumentProcessingJob.lease_expires_at <= current_time,
        )
        .with_for_update(skip_locked=True)
    ).all()
    recovered = 0
    for job in expired:
        job.lease_token = None
        job.lease_expires_at = None
        if job.attempts >= job.max_attempts:
            job.status = ExtractionJobStatus.FAILED
            job.finished_at = current_time
            job.error_message = "Worker lease expired after the maximum number of attempts."
            extraction = db.scalar(
                select(DocumentExtraction).where(DocumentExtraction.version_id == job.version_id)
            )
            if extraction is not None:
                extraction.status = ExtractionStatus.FAILED
                extraction.error_message = job.error_message
        else:
            job.status = ExtractionJobStatus.QUEUED
            job.error_message = "Previous worker lease expired; job returned to the queue."
            extraction = db.scalar(
                select(DocumentExtraction).where(DocumentExtraction.version_id == job.version_id)
            )
            if extraction is not None:
                extraction.status = ExtractionStatus.QUEUED
                extraction.error_message = job.error_message
        recovered += 1
    if recovered:
        db.commit()
    return recovered


def claim_next_job(db: Session) -> UUID | None:
    """Atomically claim one job with PostgreSQL SKIP LOCKED and a fenced lease."""
    recover_expired_jobs(db)
    job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.status == ExtractionJobStatus.QUEUED)
        .order_by(DocumentProcessingJob.created_at, DocumentProcessingJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    now = time.time()
    job.status = ExtractionJobStatus.PROCESSING
    job.attempts += 1
    job.started_at = now
    job.lease_expires_at = now + get_settings().document_job_lease_seconds
    job.lease_token = uuid4()
    db.commit()
    return job.id



def heartbeat_job(job_id: UUID, lease_token: UUID) -> bool:
    """Extend a live worker lease only while its fencing token remains current."""
    with SessionLocal() as db:
        job = db.scalar(
            select(DocumentProcessingJob)
            .where(DocumentProcessingJob.id == job_id)
            .with_for_update()
        )
        if (
            job is None
            or job.status != ExtractionJobStatus.PROCESSING
            or job.lease_token != lease_token
        ):
            return False
        job.lease_expires_at = time.time() + get_settings().document_job_lease_seconds
        db.commit()
        return True


def _lease_heartbeat(job_id: UUID, lease_token: UUID, stop: Event) -> None:
    """Renew a job lease during long but resource-bounded parsing and OCR."""
    lease_seconds = get_settings().document_job_lease_seconds
    interval = max(5.0, min(60.0, lease_seconds / 3))
    while not stop.wait(interval):
        try:
            if not heartbeat_job(job_id, lease_token):
                return
        except Exception:
            logger.exception("Could not renew document processing lease %s", job_id)


def _record_failure(db: Session, job_id: UUID, lease_token: UUID, exc: Exception) -> bool:
    job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.id == job_id)
        .with_for_update()
    )
    if job is None or job.status != ExtractionJobStatus.PROCESSING:
        return False
    if job.lease_token != lease_token:
        return False
    job.error_message = f"Processing failed ({type(exc).__name__})."
    job.lease_token = None
    job.lease_expires_at = None
    extraction = db.scalar(
        select(DocumentExtraction).where(DocumentExtraction.version_id == job.version_id)
    )
    if extraction is not None:
        extraction.error_message = job.error_message
        extraction.status = (
            ExtractionStatus.QUEUED
            if job.attempts < job.max_attempts
            else ExtractionStatus.FAILED
        )
    if job.attempts < job.max_attempts:
        job.status = ExtractionJobStatus.QUEUED
    else:
        job.status = ExtractionJobStatus.FAILED
        job.finished_at = time.time()
    db.commit()
    return True


def process_job(db: Session, job_id: UUID) -> bool:
    """Extract outside a DB transaction, then commit only if this worker still owns the lease."""
    job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.id == job_id)
        .options(selectinload(DocumentProcessingJob.version))
    )
    if job is None or job.status != ExtractionJobStatus.PROCESSING or job.lease_token is None:
        return False
    lease_token = job.lease_token
    version_id = job.version.id
    storage_key = job.version.storage_key
    extension = job.version.file_extension
    db.rollback()

    try:
        with open_storage_file(storage_key) as source_path:
            result = extract_document(source_path, extension, enable_ocr=True)
    except Exception as exc:
        logger.exception("Document processing failed for version %s", version_id)
        return _record_failure(db, job_id, lease_token, exc)

    current_job = db.scalar(
        select(DocumentProcessingJob)
        .where(DocumentProcessingJob.id == job_id)
        .with_for_update()
    )
    if (
        current_job is None
        or current_job.status != ExtractionJobStatus.PROCESSING
        or current_job.lease_token != lease_token
    ):
        db.rollback()
        logger.warning("Discarded stale processing result for version %s", version_id)
        return False

    extraction = db.scalar(
        select(DocumentExtraction)
        .where(DocumentExtraction.version_id == version_id)
        .options(selectinload(DocumentExtraction.segments))
    )
    if extraction is None:
        extraction = DocumentExtraction(
            version_id=version_id,
            status=ExtractionStatus.PROCESSING,
            parser_name="pending",
            parser_version="0",
            character_count=0,
            extraction_metadata={},
        )
        db.add(extraction)
        db.flush()
    else:
        for old_segment in list(extraction.segments):
            db.delete(old_segment)

    character_count = sum(len(segment.text) for segment in result.segments)
    final_status = (
        ExtractionStatus.NEEDS_OCR
        if result.needs_ocr
        else ExtractionStatus.EXTRACTED
        if result.segments
        else ExtractionStatus.EMPTY
    )
    extraction.parser_name = result.parser_name
    extraction.parser_version = result.parser_version
    extraction.page_count = result.page_count
    extraction.character_count = character_count
    extraction.extraction_metadata = result.metadata
    extraction.error_message = None
    extraction.quality_report = extraction_quality(
        character_count=character_count,
        page_count=result.page_count,
        segment_count=len(result.segments),
        status=final_status.value,
    )
    extraction.status = final_status
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
    current_job.status = ExtractionJobStatus.COMPLETED
    current_job.error_message = None
    current_job.lease_token = None
    current_job.lease_expires_at = None
    current_job.finished_at = time.time()
    db.commit()
    return True


def run_once() -> bool:
    """Claim one job and renew its lease while processing in a separate session."""
    with SessionLocal() as db:
        job_id = claim_next_job(db)
        if job_id is None:
            return False
        job = db.get(DocumentProcessingJob, job_id)
        lease_token = job.lease_token if job is not None else None
    if lease_token is None:
        return False

    stop = Event()
    heartbeat = Thread(
        target=_lease_heartbeat,
        args=(job_id, lease_token, stop),
        name=f"document-lease-{job_id}",
        daemon=True,
    )
    heartbeat.start()
    try:
        with SessionLocal() as db:
            process_job(db, job_id)
    finally:
        stop.set()
        heartbeat.join(timeout=5)
    return True

def run_worker(poll_seconds: float = 2.0) -> None:
    """Continuously consume the durable queue and recover from transient DB outages."""
    while True:
        try:
            if not run_once():
                time.sleep(poll_seconds)
        except Exception:
            logger.exception("Document worker loop encountered a transient failure.")
            time.sleep(max(poll_seconds, 5.0))


if __name__ == "__main__":
    run_worker()
