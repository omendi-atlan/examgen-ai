"""Real PostgreSQL tests for worker lease recovery and SKIP LOCKED concurrency."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import enforce_auth_rate_limit, get_db
from app.core.config import get_settings
from app.core.database import Base
from app.main import app
from app.models import (
    AcademicDocument,
    DocumentProcessingJob,
    DocumentVersion,
    ExtractionJobStatus,
    MembershipRole,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.services import document_processing, document_storage
from app.services.document_processing import claim_next_job, recover_expired_jobs
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

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
    _queued_jobs(postgres_sessions, 12)

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


def test_postgres_rate_limit_counter_is_atomic_across_concurrent_requests(
    postgres_sessions,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("198.51.100.42", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )

    def attempt() -> bool:
        with postgres_sessions() as db:
            try:
                enforce_auth_rate_limit(
                    request,
                    db,
                    scope="concurrency-test",
                    subject="same-client",
                    limit=5,
                    window_seconds=900,
                )
                return True
            except HTTPException as exc:
                assert exc.status_code == 429
                return False

    with ThreadPoolExecutor(max_workers=10) as workers:
        outcomes = list(workers.map(lambda _index: attempt(), range(20)))

    assert sum(outcomes) == 5
    assert outcomes.count(False) == 15


def test_postgres_tenant_isolation_and_role_authorization(
    postgres_sessions, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    engine = postgres_sessions.kw["bind"]
    settings = get_settings()
    previous_storage_path = settings.document_storage_path
    settings.document_storage_path = str(tmp_path / "private-sources")

    def override_get_db():
        with postgres_sessions() as session:
            yield session

    monkeypatch.setattr(
        document_storage,
        "scan_file",
        lambda _path: {"enabled": True, "status": "clean"},
    )
    app.dependency_overrides[get_db] = override_get_db

    def register_and_login(client: TestClient, email: str) -> str:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "display_name": "PostgreSQL tenant test",
                "password": "Correct-Horse-Battery-9!",
            },
        )
        assert registered.status_code == 201
        logged_in = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Correct-Horse-Battery-9!"},
        )
        assert logged_in.status_code == 200
        return logged_in.json()["access_token"]

    try:
        with TestClient(app) as client:
            owner_token = register_and_login(client, f"{uuid4()}@example.test")
            outsider_token = register_and_login(client, f"{uuid4()}@example.test")
            owner_headers = {"Authorization": f"Bearer {owner_token}"}
            outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

            owner_workspace = client.post(
                "/api/v1/workspaces",
                headers=owner_headers,
                json={"name": "Owner tenant", "slug": f"owner-{uuid4().hex[:12]}"},
            ).json()["id"]
            outsider_workspace = client.post(
                "/api/v1/workspaces",
                headers=outsider_headers,
                json={"name": "Outsider tenant", "slug": f"outsider-{uuid4().hex[:12]}"},
            ).json()["id"]

            uploaded = client.post(
                f"/api/v1/workspaces/{owner_workspace}/documents",
                headers=owner_headers,
                data={"title": "PostgreSQL isolated source"},
                files={"file": ("source.txt", b"Private source for tenant qualification", "text/plain")},
            )
            assert uploaded.status_code == 201
            document_id = uploaded.json()["id"]
            version_id = uploaded.json()["versions"][0]["id"]

            hidden = client.get(
                f"/api/v1/workspaces/{owner_workspace}/documents/{document_id}",
                headers=outsider_headers,
            )
            assert hidden.status_code == 404

            foreign_subject = client.post(
                f"/api/v1/workspaces/{outsider_workspace}/taxonomy/subjects",
                headers=outsider_headers,
                json={"name": "Foreign subject"},
            )
            foreign_topic = client.post(
                f"/api/v1/workspaces/{outsider_workspace}/taxonomy/subjects/{foreign_subject.json()['id']}/topics",
                headers=outsider_headers,
                json={"name": "Foreign topic"},
            )
            cross_tenant_classification = client.put(
                f"/api/v1/workspaces/{owner_workspace}/documents/{document_id}"
                f"/versions/{version_id}/classifications",
                headers=owner_headers,
                json={
                    "topic_ids": [foreign_topic.json()["id"]],
                    "rationale": "Must not cross workspace boundaries.",
                },
            )
            assert cross_tenant_classification.status_code == 422

            with Session(engine) as db:
                owner_membership = db.scalar(
                    select(WorkspaceMembership).where(
                        WorkspaceMembership.workspace_id == UUID(owner_workspace)
                    )
                )
                assert owner_membership is not None
                owner_membership.role = MembershipRole.STUDENT
                db.commit()

            student_forbidden = client.get(
                f"/api/v1/workspaces/{owner_workspace}/documents",
                headers=owner_headers,
            )
            assert student_forbidden.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.document_storage_path = previous_storage_path


def test_postgres_academic_routes_enforce_role_and_tenant_boundaries(
    postgres_sessions, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise route dependencies against PostgreSQL, not only the SQLite API fixture."""
    settings = get_settings()
    previous_storage_path = settings.document_storage_path
    settings.document_storage_path = str(tmp_path / "postgres-route-matrix")
    app.state.test_engine = postgres_sessions.kw["bind"]

    def override_get_db():
        with postgres_sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    def register_workspace(client: TestClient, email: str) -> tuple[str, str]:
        password = "Correct-Horse-Battery-9!"
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "display_name": "PostgreSQL matrix", "password": password},
        )
        assert registered.status_code == 201
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        workspace = client.post(
            "/api/v1/workspaces",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "PostgreSQL matrix", "slug": f"pg-{uuid4().hex[:12]}"},
        )
        assert workspace.status_code == 201
        return token, workspace.json()["id"]

    try:
        with TestClient(app) as client:
            owner_token, owner_workspace = register_workspace(
                client, "postgres-route-owner@example.test"
            )
            outsider_token, outsider_workspace = register_workspace(
                client, "postgres-route-outsider@example.test"
            )
            source = client.post(
                f"/api/v1/workspaces/{owner_workspace}/documents",
                headers={"Authorization": f"Bearer {owner_token}"},
                data={"title": "PostgreSQL authorization source"},
                files={"file": ("source.txt", b"PostgreSQL source text", "text/plain")},
            )
            assert source.status_code == 201
            document_id = source.json()["id"]
            version_id = source.json()["versions"][0]["id"]
            subject = client.post(
                f"/api/v1/workspaces/{owner_workspace}/taxonomy/subjects",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"name": "PostgreSQL subject"},
            )
            assert subject.status_code == 201
            topic = client.post(
                f"/api/v1/workspaces/{owner_workspace}/taxonomy/subjects/{subject.json()['id']}/topics",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"name": "PostgreSQL topic"},
            )
            assert topic.status_code == 201

            foreign_headers = {"Authorization": f"Bearer {outsider_token}"}
            cross_tenant_requests = [
                client.get(
                    f"/api/v1/workspaces/{outsider_workspace}/documents/{document_id}",
                    headers=foreign_headers,
                ),
                client.get(
                    f"/api/v1/workspaces/{outsider_workspace}/documents/{document_id}/versions/{version_id}/segments",
                    headers=foreign_headers,
                ),
                client.get(
                    f"/api/v1/workspaces/{outsider_workspace}/documents/{document_id}/versions/{version_id}/extraction-reviews",
                    headers=foreign_headers,
                ),
                client.put(
                    f"/api/v1/workspaces/{outsider_workspace}/documents/{document_id}/versions/{version_id}/classifications",
                    headers=foreign_headers,
                    json={"topic_ids": [topic.json()["id"]], "rationale": "Cross-tenant test"},
                ),
            ]
            assert [response.status_code for response in cross_tenant_requests] == [
                404,
                404,
                404,
                404,
            ]

            with postgres_sessions() as db:
                membership = db.scalar(
                    select(WorkspaceMembership).where(
                        WorkspaceMembership.workspace_id == UUID(owner_workspace)
                    )
                )
                assert membership is not None
                membership.role = MembershipRole.STUDENT
                db.commit()

            student_headers = {"Authorization": f"Bearer {owner_token}"}
            student_requests = [
                client.get(
                    f"/api/v1/workspaces/{owner_workspace}/documents",
                    headers=student_headers,
                ),
                client.get(
                    f"/api/v1/workspaces/{owner_workspace}/documents/{document_id}",
                    headers=student_headers,
                ),
                client.get(
                    f"/api/v1/workspaces/{owner_workspace}/taxonomy/subjects",
                    headers=student_headers,
                ),
                client.post(
                    f"/api/v1/workspaces/{owner_workspace}/taxonomy/subjects",
                    headers=student_headers,
                    json={"name": "Forbidden PostgreSQL subject"},
                ),
            ]
            assert [response.status_code for response in student_requests] == [
                403,
                403,
                403,
                403,
            ]
    finally:
        app.dependency_overrides.clear()
        settings.document_storage_path = previous_storage_path
