"""Real PostgreSQL tests for worker lease recovery and SKIP LOCKED concurrency."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from app.core.database import Base
from app.models import (
    AcademicDocument,
    DocumentProcessingJob,
    DocumentVersion,
    ExtractionJobStatus,
    User,
    Workspace,
)
from app.services import document_processing
from app.services.document_processing import claim_next_job, recover_expired_jobs
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not DATABASE_URL.startswith("postgresql"),
    reason="PostgreSQL concurrency tests require TEST_DATABASE_URL.",
)


@pytest.fixture
def postgres_sessions():
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _queued_jobs(factory, count: int) -> list[UUID]:
    with factory() as db:
        user = User(email=f"{uuid4()}@example.test", display_name="Worker test")
        workspace = Workspace(name="Worker tests", slug=f"worker-{uuid4().hex[:12]}")
        db.add_all([user, workspace])
        db.flush()
        ids = []
        for index in range(count):
            document = AcademicDocument(
                workspace_id=workspace.id,
                title=f"Document {index}",
                created_by=user.id,
            )
            db.add(document)
            db.flush()
            version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                original_filename=f"source-{index}.txt",
                storage_key=f"{uuid4().hex[:2]}/{uuid4().hex}.txt",
                media_type="text/plain",
                file_extension=".txt",
                size_bytes=10,
                sha256=uuid4().hex + uuid4().hex,
                uploaded_by=user.id,
            )
            db.add(version)
            db.flush()
            job = DocumentProcessingJob(
                version_id=version.id,
                status=ExtractionJobStatus.QUEUED,
                attempts=0,
                max_attempts=3,
            )
            db.add(job)
            db.flush()
            ids.append(job.id)
        db.commit()
        return ids


def test_postgres_workers_claim_distinct_jobs_concurrently(postgres_sessions) -> None:
    _queued_jobs(postgres_sessions, 2)

    def claim_one():
        with postgres_sessions() as db:
            return claim_next_job(db)

    with ThreadPoolExecutor(max_workers=2) as workers:
        claimed = list(workers.map(lambda _index: claim_one(), range(2)))

    assert all(claimed)
    assert len(set(claimed)) == 2


def test_expired_worker_lease_is_requeued_and_token_revoked(postgres_sessions) -> None:
    job_id = _queued_jobs(postgres_sessions, 1)[0]
    with postgres_sessions() as db:
        job = db.get(DocumentProcessingJob, job_id)
        job.status = ExtractionJobStatus.PROCESSING
        job.attempts = 1
        job.lease_token = uuid4()
        job.lease_expires_at = time.time() - 5
        db.commit()

    with postgres_sessions() as db:
        recovered = recover_expired_jobs(db)

    with postgres_sessions() as db:
        job = db.scalar(select(DocumentProcessingJob).where(DocumentProcessingJob.id == job_id))
        assert recovered == 1
        assert job.status == ExtractionJobStatus.QUEUED
        assert job.lease_token is None
        assert job.lease_expires_at is None


def test_expired_job_at_attempt_limit_is_terminal(postgres_sessions) -> None:
    job_id = _queued_jobs(postgres_sessions, 1)[0]
    with postgres_sessions() as db:
        job = db.get(DocumentProcessingJob, job_id)
        job.status = ExtractionJobStatus.PROCESSING
        job.attempts = job.max_attempts
        job.lease_token = uuid4()
        job.lease_expires_at = time.time() - 5
        db.commit()

    with postgres_sessions() as db:
        recovered = recover_expired_jobs(db)

    with postgres_sessions() as db:
        job = db.get(DocumentProcessingJob, job_id)
        assert recovered == 1
        assert job.status == ExtractionJobStatus.FAILED
        assert job.finished_at is not None
        assert job.lease_token is None



def test_worker_heartbeat_extends_only_the_current_lease(
    postgres_sessions, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = _queued_jobs(postgres_sessions, 1)[0]
    token = uuid4()
    with postgres_sessions() as db:
        job = db.get(DocumentProcessingJob, job_id)
        job.status = ExtractionJobStatus.PROCESSING
        job.attempts = 1
        job.lease_token = token
        job.lease_expires_at = time.time() + 30
        original_expiry = job.lease_expires_at
        db.commit()
    monkeypatch.setattr(document_processing, "SessionLocal", postgres_sessions)

    assert document_processing.heartbeat_job(job_id, token) is True
    with postgres_sessions() as db:
        job = db.get(DocumentProcessingJob, job_id)
        assert job.lease_expires_at > original_expiry
        job.lease_token = uuid4()
        db.commit()

    assert document_processing.heartbeat_job(job_id, token) is False
