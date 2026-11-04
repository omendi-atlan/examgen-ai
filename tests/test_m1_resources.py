"""Milestone 1 — subject-specific resource management, isolation and provenance."""

from __future__ import annotations

import io

from .conftest import make_previous_paper, make_text_document


def _create_workspace(client, auth, name="Data Structures and Algorithms"):
    response = client.post("/api/workspaces", json={
        "name": name, "code": "CS201", "module": "Module 3",
        "institution": "University of Example"}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, auth, workspace_id, filename, content):
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_creation_and_isolation(client, auth):
    first = _create_workspace(client, auth, "Algorithms")
    second = _create_workspace(client, auth, "Databases")

    _upload(client, auth, first["id"], "algorithms.txt", make_text_document())
    _upload(client, auth, second["id"], "databases.txt",
            b"Normalisation is the process of organising data to reduce redundancy.")

    first_docs = client.get(f"/api/workspaces/{first['id']}/documents", headers=auth).json()
    second_docs = client.get(f"/api/workspaces/{second['id']}/documents", headers=auth).json()

    assert [d["filename"] for d in first_docs] == ["algorithms.txt"]
    assert [d["filename"] for d in second_docs] == ["databases.txt"]

    # A document from one workspace must not be reachable through the other.
    response = client.get(
        f"/api/workspaces/{second['id']}/documents/{first_docs[0]['id']}/content",
        headers=auth)
    assert response.status_code == 404


def test_workspaces_are_private_to_their_owner(client, auth):
    workspace = _create_workspace(client, auth, "Private Subject")

    other = client.post("/api/auth/register", json={
        "email": "someone-else@example.com", "password": "another-good-password",
        "display_name": "Other"}).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other}"}

    assert client.get("/api/workspaces", headers=other_headers).json() == []
    response = client.get(f"/api/workspaces/{workspace['id']}", headers=other_headers)
    assert response.status_code == 404


def test_upload_extracts_content_and_records_provenance(client, auth):
    workspace = _create_workspace(client, auth)
    document = _upload(client, auth, workspace["id"], "notes.txt", make_text_document())

    assert document["status"] == "extracted"
    assert document["extracted_chars"] > 1000

    chunks = client.get(
        f"/api/workspaces/{workspace['id']}/documents/{document['id']}/content",
        headers=auth).json()
    assert len(chunks) > 5
    assert all(chunk["provenance"] == "coursework" for chunk in chunks)
    assert any(chunk["kind"] == "heading" for chunk in chunks)


def test_additional_resources_do_not_restart_the_workspace(client, auth):
    workspace = _create_workspace(client, auth)
    first = _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    topics_before = client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json()
    assert topics_before

    _upload(client, auth, workspace["id"], "paper.txt", make_previous_paper())

    documents = client.get(f"/api/workspaces/{workspace['id']}/documents", headers=auth).json()
    assert len(documents) == 2
    # The original document is untouched and still present.
    assert any(d["id"] == first["id"] for d in documents)


def test_document_versioning_on_reupload(client, auth):
    workspace = _create_workspace(client, auth)
    first = _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    assert first["version"] == 1

    second = _upload(client, auth, workspace["id"], "notes.txt",
                     make_text_document() + b"\n\nChapter 6. Revision Summary\nA summary.")
    assert second["version"] == 2
    assert second["is_latest"] is True

    latest = client.get(f"/api/workspaces/{workspace['id']}/documents", headers=auth).json()
    assert len(latest) == 1 and latest[0]["version"] == 2

    history = client.get(
        f"/api/workspaces/{workspace['id']}/documents?include_history=true",
        headers=auth).json()
    assert len(history) == 2
    assert {h["version"] for h in history} == {1, 2}


def test_duplicate_content_is_detected_not_duplicated_silently(client, auth):
    workspace = _create_workspace(client, auth)
    _upload(client, auth, workspace["id"], "a.txt", make_text_document())
    duplicate = _upload(client, auth, workspace["id"], "b.txt", make_text_document())
    assert "Identical content already uploaded" in duplicate["processing_notes"]


def test_classification_produces_topics_outcomes_and_sufficiency(client, auth):
    workspace = _create_workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())

    report = client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth).json()
    assert report["verdict"] in {"sufficient", "partial"}
    assert report["adequate"]
    assert report["document_count"] == 1
    assert report["total_chars"] > 1000

    topics = client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json()
    assert len(topics) >= 3
    names = " ".join(t["name"].lower() for t in topics)
    assert "sort" in names or "algorithm" in names or "data structure" in names

    outcomes = [o for t in topics for s in t["subtopics"] for o in s["outcomes"]]
    assert outcomes, "expected learning outcomes to be extracted"
    assert all(o["bloom"] in
               {"remember", "understand", "apply", "analyse", "evaluate", "create"}
               for o in outcomes)


def test_sufficiency_reports_missing_content_without_fabricating(client, auth):
    workspace = _create_workspace(client, auth)
    # A previous paper that references material absent from the coursework.
    _upload(client, auth, workspace["id"], "paper.txt", make_previous_paper())

    report = client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth).json()
    assert report["verdict"] in {"insufficient", "partial"}
    # Thin material must not be reported as sufficient.
    assert report["verdict"] != "sufficient"


def test_empty_workspace_reports_insufficient_not_invented_content(client, auth):
    workspace = _create_workspace(client, auth, "Empty Subject")
    report = client.get(f"/api/workspaces/{workspace['id']}/sufficiency", headers=auth).json()
    assert report["verdict"] == "insufficient"
    assert report["document_count"] == 0
    assert client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json() == []


def test_student_can_correct_topic_classification(client, auth):
    workspace = _create_workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    topics = client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json()

    target = topics[0]
    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/topics/{target['id']}",
        json={"name": "Corrected Topic Name", "needs_visual": "essential"}, headers=auth)
    assert updated.status_code == 200
    assert updated.json()["name"] == "Corrected Topic Name"
    assert updated.json()["reviewed_by_student"] is True

    # The correction survives reclassification.
    client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    after = client.get(f"/api/workspaces/{workspace['id']}/topics", headers=auth).json()
    corrected = [t for t in after if t["name"] == "Corrected Topic Name"]
    assert corrected and corrected[0]["needs_visual"] == "essential"


def test_unsupported_file_type_is_rejected(client, auth):
    workspace = _create_workspace(client, auth)
    response = client.post(
        f"/api/workspaces/{workspace['id']}/documents",
        files={"file": ("virus.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        headers=auth)
    assert response.status_code == 415
