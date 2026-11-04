"""Academic ingestion, provenance, extraction and taxonomy API tests."""

from uuid import UUID

import pytest
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.models import DocumentProcessingJob
from app.services.document_processing import claim_next_job, process_job
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    previous_storage = get_settings().document_storage_path
    previous_limit = get_settings().max_document_upload_bytes
    get_settings().document_storage_path = str(tmp_path / "private-documents")
    get_settings().max_document_upload_bytes = 1024 * 1024
    app.state.test_engine = engine

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings().document_storage_path = previous_storage
    get_settings().max_document_upload_bytes = previous_limit


def create_workspace(client: TestClient, email: str = "examiner@example.test") -> tuple[str, str]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Examiner",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct-Horse-Battery-9!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    workspace = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Academic Workspace", "slug": f"academic-{email.split('@')[0]}"},
    )
    assert workspace.status_code == 201
    return token, workspace.json()["id"]


def test_text_upload_extracts_and_retains_provenance(client: TestClient) -> None:
    token, workspace_id = create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "title": "Introduction to Algorithms",
            "source_type": "lecture_notes",
            "source_reference": "BC-ICT-2026-001",
            "publisher": "Belgium Campus",
            "published_on": "2026-09-15",
        },
        files={"file": ("algorithms.txt", b"Sorting\nSearching\nGraph traversal", "text/plain")},
    )
    assert response.status_code == 201
    queued_document = response.json()
    assert queued_document["current_version_number"] == 1
    assert queued_document["versions"][0]["extraction"]["status"] == "queued"
    with Session(app.state.test_engine) as db:
        job_id = claim_next_job(db)
        assert job_id is not None
        assert process_job(db, job_id) is True
    refreshed = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{queued_document['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert refreshed.status_code == 200
    document = refreshed.json()
    version = document["versions"][0]
    assert version["version_number"] == 1
    assert version["sha256"] and len(version["sha256"]) == 64
    assert version["source_reference"] == "BC-ICT-2026-001"
    assert version["publisher"] == "Belgium Campus"
    assert version["published_on"] == "2026-09-15"
    assert version["extraction"]["status"] == "extracted"
    assert version["extraction"]["character_count"] > 0
    assert version["extraction"]["quality_report"]["automatically_approved"] is False

    segments = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}"
        f"/versions/{version['id']}/segments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert segments.status_code == 200
    assert "Sorting" in segments.json()[0]["text"]
    assert segments.json()[0]["locator"].startswith("text:chars-")


def test_document_versions_are_immutable_and_append_only(client: TestClient) -> None:
    token, workspace_id = create_workspace(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        data={"title": "Versioned source"},
        files={"file": ("source.txt", b"Version one source", "text/plain")},
    )
    assert created.status_code == 201
    document = created.json()
    first_version = document["versions"][0]

    updated = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}/versions",
        headers=headers,
        data={"source_type": "revised_material"},
        files={"file": ("source-revised.txt", b"Version two source", "text/plain")},
    )
    assert updated.status_code == 201
    result = updated.json()
    assert result["current_version_number"] == 2
    assert [item["version_number"] for item in result["versions"]] == [1, 2]
    assert result["versions"][0]["sha256"] == first_version["sha256"]
    assert result["versions"][0]["id"] == first_version["id"]


def test_explicit_subject_topic_classification_is_persisted(client: TestClient) -> None:
    token, workspace_id = create_workspace(client)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        data={"title": "Database notes"},
        files={"file": ("database.txt", b"Relational database concepts", "text/plain")},
    )
    document = created.json()
    version_id = document["versions"][0]["id"]

    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Database Systems", "description": "Database theory and practice"},
    )
    assert subject.status_code == 201
    topic = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject.json()['id']}/topics",
        headers=headers,
        json={"name": "Relational Model"},
    )
    assert topic.status_code == 201

    classified = client.put(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}"
        f"/versions/{version_id}/classifications",
        headers=headers,
        json={"topic_ids": [topic.json()["id"]], "rationale": "Confirmed against module outline."},
    )
    assert classified.status_code == 200
    assignment = classified.json()[0]
    assert assignment["method"] == "human"
    assert assignment["subject_name"] == "Database Systems"
    assert assignment["topic_name"] == "Relational Model"

    detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}",
        headers=headers,
    )
    assert detail.json()["versions"][0]["classifications"][0]["topic_id"] == topic.json()["id"]


def test_cross_workspace_document_access_is_denied(client: TestClient) -> None:
    owner_token, workspace_id = create_workspace(client, "owner@example.test")
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {owner_token}"},
        data={"title": "Private source"},
        files={"file": ("private.txt", b"Private course content", "text/plain")},
    )
    document_id = created.json()["id"]

    outsider_token, _ = create_workspace(client, "outsider@example.test")
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert response.status_code == 404


def test_upload_rejects_mismatched_file_signature(client: TestClient) -> None:
    token, workspace_id = create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Not really a PDF"},
        files={"file": ("fake.pdf", b"plain text pretending to be a PDF", "application/pdf")},
    )
    assert response.status_code == 415


def test_upload_rejects_files_over_configured_limit(client: TestClient) -> None:
    get_settings().max_document_upload_bytes = 1024
    token, workspace_id = create_workspace(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Oversized source"},
        files={"file": ("large.txt", b"x" * 1025, "text/plain")},
    )
    assert response.status_code == 413


def test_docx_extraction_preserves_paragraph_locators(tmp_path) -> None:
    from app.services.document_extraction import extract_document

    document = WordDocument()
    document.add_paragraph("Learning outcomes and core concepts")
    document.add_paragraph("Assessment preparation and practice")
    source = tmp_path / "course.docx"
    document.save(source)

    result = extract_document(source, ".docx")
    assert result.parser_name == "python-docx"
    assert result.page_count is None
    assert result.segments[0].locator.startswith("paragraph-1:")
    assert "Learning outcomes" in result.segments[0].text


def test_upload_creates_one_durable_job_per_immutable_version(client: TestClient) -> None:
    token, workspace_id = create_workspace(client, "queue@example.test")
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Queued source"},
        files={"file": ("queued.txt", b"Queued content for worker", "text/plain")},
    )
    assert response.status_code == 201
    version_id = response.json()["versions"][0]["id"]
    with Session(app.state.test_engine) as db:
        jobs = db.scalars(
            select(DocumentProcessingJob).where(
                DocumentProcessingJob.version_id == UUID(version_id)
            )
        ).all()
        assert len(jobs) == 1
        assert jobs[0].status.value == "queued"


def test_extraction_review_is_human_audited_and_append_only(client: TestClient) -> None:
    from app.models import AuditEvent, DocumentExtractionReview

    token, workspace_id = create_workspace(client, "reviewer@example.test")
    headers = {"Authorization": f"Bearer {token}"}
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        data={"title": "Reviewable course notes"},
        files={"file": ("notes.txt", b"Core learning outcomes and assessment concepts.", "text/plain")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    version_id = uploaded.json()["versions"][0]["id"]

    queued_review = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews",
        headers=headers,
        json={"decision": "accepted", "rationale": "Looks suitable."},
    )
    assert queued_review.status_code == 409

    with Session(app.state.test_engine) as db:
        job_id = claim_next_job(db)
        assert job_id is not None
        assert process_job(db, job_id) is True

    rejected = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews",
        headers=headers,
        json={"decision": "rejected", "rationale": "Please verify the source formatting."},
    )
    assert rejected.status_code == 201
    assert rejected.json()["decision"] == "rejected"

    accepted = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews",
        headers=headers,
        json={"decision": "accepted", "rationale": "Reviewed against the original source."},
    )
    assert accepted.status_code == 201
    history = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews",
        headers=headers,
    )
    assert history.status_code == 200
    assert sorted(item["decision"] for item in history.json()) == ["accepted", "rejected"]

    with Session(app.state.test_engine) as db:
        reviews = db.scalars(
            select(DocumentExtractionReview).where(DocumentExtractionReview.version_id == UUID(version_id))
        ).all()
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.workspace_id == UUID(workspace_id),
                AuditEvent.resource_id == version_id,
                AuditEvent.action.in_([
                    "academic_document.extraction_rejected",
                    "academic_document.extraction_accepted",
                ]),
            )
        ).all()
        assert len(reviews) == 2
        assert len(events) == 2


def test_extraction_review_is_workspace_isolated(client: TestClient) -> None:
    owner_token, workspace_id = create_workspace(client, "review-owner@example.test")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=owner_headers,
        data={"title": "Private review source"},
        files={"file": ("private.txt", b"Private source material", "text/plain")},
    )
    document_id = uploaded.json()["id"]
    version_id = uploaded.json()["versions"][0]["id"]

    outsider_token, _ = create_workspace(client, "review-outsider@example.test")
    denied = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert denied.status_code == 404


def test_student_role_cannot_access_examiner_ingestion_endpoints(client: TestClient) -> None:
    from app.models import MembershipRole, WorkspaceMembership

    token, workspace_id = create_workspace(client, "student-role@example.test")
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Restricted source"},
        files={"file": ("restricted.txt", b"Examiner-only academic source", "text/plain")},
    )
    assert created.status_code == 201

    with Session(app.state.test_engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id)
            )
        )
        assert membership is not None
        membership.role = MembershipRole.STUDENT
        db.commit()

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_classification_rejects_topic_from_another_workspace(client: TestClient) -> None:
    owner_token, owner_workspace = create_workspace(client, "taxonomy-owner@example.test")
    source = client.post(
        f"/api/v1/workspaces/{owner_workspace}/documents",
        headers={"Authorization": f"Bearer {owner_token}"},
        data={"title": "Owner source"},
        files={"file": ("owner.txt", b"Owner workspace source", "text/plain")},
    )
    document_id = source.json()["id"]
    version_id = source.json()["versions"][0]["id"]

    other_token, other_workspace = create_workspace(client, "taxonomy-other@example.test")
    subject = client.post(
        f"/api/v1/workspaces/{other_workspace}/taxonomy/subjects",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Other workspace subject"},
    )
    topic = client.post(
        f"/api/v1/workspaces/{other_workspace}/taxonomy/subjects/{subject.json()['id']}/topics",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Private topic"},
    )

    rejected = client.put(
        f"/api/v1/workspaces/{owner_workspace}/documents/{document_id}"
        f"/versions/{version_id}/classifications",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"topic_ids": [topic.json()["id"]], "rationale": "Attempted cross-tenant assignment."},
    )
    assert rejected.status_code == 422


def _academic_route_matrix(
    client: TestClient,
    workspace_id: str,
    document_id: str,
    version_id: str,
    subject_id: str,
    topic_id: str,
    token: str,
) -> list[tuple[str, str, dict[str, object]]]:
    """Build representative requests for every workspace-scoped academic route."""
    headers = {"Authorization": f"Bearer {token}"}
    return [
        ("post", f"/api/v1/workspaces/{workspace_id}/documents", {
            "headers": headers,
            "data": {"title": "Authorization matrix upload"},
            "files": {"file": ("matrix.txt", b"matrix source", "text/plain")},
        }),
        ("post", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions", {
            "headers": headers,
            "files": {"file": ("matrix-v2.txt", b"matrix source version two", "text/plain")},
        }),
        ("get", f"/api/v1/workspaces/{workspace_id}/documents", {"headers": headers}),
        ("get", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}", {"headers": headers}),
        ("get", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/segments", {"headers": headers}),
        ("post", f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects", {
            "headers": headers,
            "json": {"name": "Authorization Matrix Subject"},
        }),
        ("get", f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects", {"headers": headers}),
        ("post", f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics", {
            "headers": headers,
            "json": {"name": "Authorization Matrix Topic"},
        }),
        ("get", f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics", {"headers": headers}),
        ("put", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/classifications", {
            "headers": headers,
            "json": {"topic_ids": [topic_id], "rationale": "Authorization matrix test"},
        }),
        ("post", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews", {
            "headers": headers,
            "json": {"decision": "rejected", "rationale": "Authorization matrix test"},
        }),
        ("get", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/extraction-reviews", {
            "headers": headers,
        }),
    ]


def _create_matrix_resources(client: TestClient, token: str, workspace_id: str) -> tuple[str, str, str, str]:
    document = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": "Authorization matrix source"},
        files={"file": ("matrix-source.txt", b"source text for authorization", "text/plain")},
    )
    assert document.status_code == 201
    document_id = document.json()["id"]
    version_id = document.json()["versions"][0]["id"]
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Authorization matrix taxonomy"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]
    topic = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Authorization matrix topic"},
    )
    assert topic.status_code == 201
    return document_id, version_id, subject_id, topic.json()["id"]


def test_all_academic_routes_require_editor_role(client: TestClient) -> None:
    from app.models import MembershipRole, WorkspaceMembership

    token, workspace_id = create_workspace(client, "route-matrix-student@example.test")
    document_id, version_id, subject_id, topic_id = _create_matrix_resources(
        client, token, workspace_id
    )
    with Session(app.state.test_engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id)
            )
        )
        assert membership is not None
        membership.role = MembershipRole.STUDENT
        db.commit()

    for method, path, kwargs in _academic_route_matrix(
        client, workspace_id, document_id, version_id, subject_id, topic_id, token
    ):
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, f"{method.upper()} {path}: {response.status_code} {response.text}"


def test_all_academic_routes_hide_resources_from_other_workspaces(client: TestClient) -> None:
    owner_token, owner_workspace = create_workspace(client, "route-matrix-owner@example.test")
    outsider_token, outsider_workspace = create_workspace(client, "route-matrix-outsider@example.test")
    document_id, version_id, subject_id, topic_id = _create_matrix_resources(
        client, owner_token, owner_workspace
    )

    for method, path, kwargs in _academic_route_matrix(
        client, outsider_workspace, document_id, version_id, subject_id, topic_id, outsider_token
    ):
        response = getattr(client, method)(path, **kwargs)
        if path.endswith("/documents") and method == "post":
            expected_status = 201
        elif path.endswith("/taxonomy/subjects") and method == "post":
            expected_status = 201
        elif path.endswith("/documents") or path.endswith("/taxonomy/subjects"):
            expected_status = 200
        else:
            expected_status = 404
        assert response.status_code == expected_status, (
            f"{method.upper()} {path}: {response.status_code} {response.text}"
        )


def test_academic_upload_rate_limit_is_shared_and_returns_retry_after(
    client: TestClient,
) -> None:
    token, workspace_id = create_workspace(client, "upload-rate-limit@example.test")
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        data={"title": "Rate-limited source 0"},
        files={"file": ("source-0.txt", b"Unique academic source content 0", "text/plain")},
    )
    assert first.status_code == 201
    document_id = first.json()["id"]

    for index in range(1, 10):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            headers=headers,
            data={"title": f"Rate-limited source {index}"},
            files={
                "file": (
                    f"source-{index}.txt",
                    f"Unique academic source content {index}".encode(),
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201

    for index in range(10):
        response = client.post(
            f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions",
            headers=headers,
            files={
                "file": (
                    f"source-version-{index}.txt",
                    f"Unique academic version content {index}".encode(),
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201

    limited = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=headers,
        data={"title": "Upload beyond hourly limit"},
        files={"file": ("source-over-limit.txt", b"Unique source beyond limit", "text/plain")},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


def test_student_coursework_resources_are_private_and_subject_scoped(client: TestClient) -> None:
    from app.models import MembershipRole, MembershipStatus, User, WorkspaceMembership

    owner_token, workspace_id = create_workspace(client, "coursework-owner@example.test")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=owner_headers,
        json={"name": "INL201"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]
    other_subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=owner_headers,
        json={"name": "INL202"},
    )
    assert other_subject.status_code == 201

    with Session(app.state.test_engine) as db:
        owner_membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id)
            )
        )
        assert owner_membership is not None
        owner_membership.role = MembershipRole.STUDENT
        db.commit()

    available_subjects = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects",
        headers=owner_headers,
    )
    assert available_subjects.status_code == 200
    assert subject_id in [item["id"] for item in available_subjects.json()]

    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=owner_headers,
        data={"title": "INL201 lecture notes"},
        files={"file": ("lecture.txt", b"Variables, functions and control flow.", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    resource = uploaded.json()
    assert resource["subject_id"] == subject_id
    assert resource["visibility"] == "private"
    assert resource["versions"][0]["extraction"]["status"] == "queued"

    listed = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=owner_headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [resource["id"]]

    wrong_subject = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects/{other_subject.json()['id']}/resources/{resource['id']}",
        headers=owner_headers,
    )
    assert wrong_subject.status_code == 404

    second_user_email = "coursework-second-student@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": second_user_email,
            "display_name": "Second student",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": second_user_email, "password": "Correct-Horse-Battery-9!"},
    )
    assert login.status_code == 200
    second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with Session(app.state.test_engine) as db:
        second_user = db.scalar(select(User).where(User.email == second_user_email))
        assert second_user is not None
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=second_user.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    hidden = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources/{resource['id']}",
        headers=second_headers,
    )
    assert hidden.status_code == 404

    forbidden_staff_listing = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents",
        headers=owner_headers,
    )
    assert forbidden_staff_listing.status_code == 403


def test_coursework_cohort_sharing_requires_staff_policy(client: TestClient) -> None:
    from app.models import MembershipRole, WorkspaceMembership

    token, workspace_id = create_workspace(client, "coursework-sharing@example.test")
    headers = {"Authorization": f"Bearer {token}"}
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Shared Module"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]

    with Session(app.state.test_engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id)
            )
        )
        assert membership is not None
        membership.role = MembershipRole.STUDENT
        db.commit()

    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=headers,
        data={"title": "Unapproved cohort notes", "visibility": "cohort"},
        files={"file": ("notes.txt", b"Shared notes", "text/plain")},
    )
    assert denied.status_code == 409


def test_staff_enabled_cohort_resources_are_visible_only_while_policy_is_enabled(
    client: TestClient,
) -> None:
    from app.models import MembershipRole, MembershipStatus, User, WorkspaceMembership

    owner_token, workspace_id = create_workspace(client, "coursework-cohort-owner@example.test")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=owner_headers,
        json={"name": "Cohort Sharing Module"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]

    enabled = client.put(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resource-sharing",
        headers=owner_headers,
        json={"enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["resource_sharing_enabled"] is True

    second_email = "coursework-cohort-member@example.test"
    assert client.post(
        "/api/v1/auth/register",
        json={
            "email": second_email,
            "display_name": "Cohort member",
            "password": "Correct-Horse-Battery-9!",
        },
    ).status_code == 201
    second_login = client.post(
        "/api/v1/auth/login",
        json={"email": second_email, "password": "Correct-Horse-Battery-9!"},
    )
    assert second_login.status_code == 200
    second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}

    with Session(app.state.test_engine) as db:
        owner_membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id),
                WorkspaceMembership.role == MembershipRole.OWNER,
            )
        )
        assert owner_membership is not None
        owner_membership.role = MembershipRole.STUDENT
        second_user = db.scalar(select(User).where(User.email == second_email))
        assert second_user is not None
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=second_user.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    shared = client.post(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=owner_headers,
        data={"title": "Approved cohort notes", "visibility": "cohort"},
        files={"file": ("cohort.txt", b"Notes shared by the lecturer-approved cohort policy.", "text/plain")},
    )
    assert shared.status_code == 201, shared.text
    resource_id = shared.json()["id"]

    visible = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=second_headers,
    )
    assert visible.status_code == 200
    assert resource_id in [item["id"] for item in visible.json()]

    student_policy_denied = client.put(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resource-sharing",
        headers=owner_headers,
        json={"enabled": False},
    )
    assert student_policy_denied.status_code == 403

    with Session(app.state.test_engine) as db:
        owner_membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(workspace_id),
                WorkspaceMembership.user_id == UUID(shared.json()["created_by"]),
            )
        )
        assert owner_membership is not None
        owner_membership.role = MembershipRole.OWNER
        db.commit()

    disabled = client.put(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resource-sharing",
        headers=owner_headers,
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    hidden = client.get(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources/{resource_id}",
        headers=second_headers,
    )
    assert hidden.status_code == 404
