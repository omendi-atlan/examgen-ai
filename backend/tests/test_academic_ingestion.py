"""Academic ingestion, provenance, extraction and taxonomy API tests."""

import pytest

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
    document = response.json()
    assert document["current_version_number"] == 1
    version = document["versions"][0]
    assert version["version_number"] == 1
    assert version["sha256"] and len(version["sha256"]) == 64
    assert version["source_reference"] == "BC-ICT-2026-001"
    assert version["publisher"] == "Belgium Campus"
    assert version["published_on"] == "2026-09-15"
    assert version["extraction"]["status"] == "extracted"
    assert version["extraction"]["character_count"] > 0

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
