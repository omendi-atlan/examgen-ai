"""Subject assistant — grounded chatbot acceptance tests.

These tests assert the properties that make the assistant safe to ship:

* answers are grounded in the workspace's own coursework and carry citations;
* the assistant refuses to invent content when nothing relevant exists;
* navigational intents are answered from persisted records, not guesses;
* conversations are persisted and resume across requests;
* subject isolation and ownership are enforced on every route.
"""

from __future__ import annotations

import io

from .conftest import make_previous_paper, make_text_document


def _workspace(client, auth, name="Data Structures and Algorithms"):
    response = client.post("/api/workspaces", json={
        "name": name, "code": "CS201"}, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, auth, workspace_id, filename, content):
    response = client.post(
        f"/api/workspaces/{workspace_id}/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
        headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _ask(client, auth, workspace_id, message, session_id=None):
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    response = client.post(f"/api/workspaces/{workspace_id}/assistant/ask",
                           json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_prompts_endpoint_is_public_and_static(client):
    response = client.get("/api/assistant/prompts")
    assert response.status_code == 200
    body = response.json()
    assert body["prompts"] and body["greeting"]
    # The public endpoint must never expose workspace content.
    assert "citations" not in body


def test_explanation_is_grounded_and_cited(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())

    result = _ask(client, auth, workspace["id"],
                  "What is the time complexity of merge sort?")
    message = result["message"]

    assert message["intent"] == "explain"
    assert message["grounded"] is True
    assert message["citations"], "a grounded answer must cite its source"
    citation = message["citations"][0]
    assert citation["document_name"] == "notes.txt"
    assert citation["excerpt"]
    # The excerpt actually came from the uploaded coursework.
    assert "merge sort" in message["content"].lower()


def test_assistant_refuses_to_invent_content(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())

    result = _ask(client, auth, workspace["id"],
                  "Explain the Krebs cycle in cellular respiration")
    message = result["message"]

    assert message["grounded"] is False
    assert not message["citations"]
    assert "could not find" in message["content"].lower()
    # It must not fabricate an answer about material it does not have.
    assert "krebs" not in message["content"].lower()


def test_navigational_intents_answer_from_records(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    _upload(client, auth, workspace["id"], "paper.txt", make_previous_paper())
    classify = client.post(f"/api/workspaces/{workspace['id']}/classify", headers=auth)
    assert classify.status_code == 200, classify.text

    topics = _ask(client, auth, workspace["id"], "What topics does this subject cover?")
    assert topics["message"]["intent"] == "topics"
    assert "topic" in topics["message"]["content"].lower()

    gaps = _ask(client, auth, workspace["id"], "What is missing from my coursework?")
    assert gaps["message"]["intent"] == "gaps"
    assert "verdict" in gaps["message"]["content"].lower()

    visuals = _ask(client, auth, workspace["id"], "Which topics need diagrams?")
    assert visuals["message"]["intent"] == "visuals"

    progress = _ask(client, auth, workspace["id"], "How am I performing in this subject?")
    assert progress["message"]["intent"] == "progress"
    # With no submitted attempts the assistant must say so rather than guess.
    assert progress["message"]["grounded"] is False
    assert "no submitted attempts" in progress["message"]["content"].lower()

    study = _ask(client, auth, workspace["id"],
                 "How should I prepare for the examination?")
    assert study["message"]["intent"] == "study"


def test_conversation_persists_and_resumes(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())

    first = _ask(client, auth, workspace["id"], "What is a stack?")
    session_id = first["session"]["id"]

    second = _ask(client, auth, workspace["id"], "What is a queue?", session_id)
    assert second["session"]["id"] == session_id

    detail = client.get(
        f"/api/workspaces/{workspace['id']}/assistant/sessions/{session_id}",
        headers=auth)
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    # A session created implicitly by /ask holds only the exchanged turns; the
    # greeting is added by POST /sessions, which the UI calls first.
    roles = [m["role"] for m in messages]
    assert roles == ["user", "assistant", "user", "assistant"]

    listed = client.get(f"/api/workspaces/{workspace['id']}/assistant/sessions",
                        headers=auth).json()
    assert [s["id"] for s in listed] == [session_id]
    # The conversation title is derived from the first question.
    assert "stack" in listed[0]["title"].lower()


def test_session_can_be_deleted(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    session_id = _ask(client, auth, workspace["id"], "What is a stack?")["session"]["id"]

    removed = client.delete(
        f"/api/workspaces/{workspace['id']}/assistant/sessions/{session_id}", headers=auth)
    assert removed.status_code == 204
    assert client.get(
        f"/api/workspaces/{workspace['id']}/assistant/sessions/{session_id}",
        headers=auth).status_code == 404


def test_answers_are_scoped_to_the_selected_subject(client, auth):
    """The assistant must never cite another subject's coursework."""
    algorithms = _workspace(client, auth, "Algorithms")
    databases = _workspace(client, auth, "Databases")
    _upload(client, auth, algorithms["id"], "algorithms.txt", make_text_document())
    _upload(client, auth, databases["id"], "databases.txt",
            b"Normalisation is the process of organising data to reduce redundancy. "
            b"A foreign key references a primary key in another relation.")

    result = _ask(client, auth, algorithms["id"], "What is normalisation?")
    message = result["message"]
    if message["citations"]:
        assert all(c["document_name"] == "algorithms.txt" for c in message["citations"])
    assert "databases.txt" not in message["content"]


def test_assistant_requires_authentication(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    assert client.post(f"/api/workspaces/{workspace['id']}/assistant/ask",
                       json={"message": "hi"}).status_code == 401


def test_assistant_enforces_workspace_ownership(client, auth):
    workspace = _workspace(client, auth)
    _upload(client, auth, workspace["id"], "notes.txt", make_text_document())
    session_id = _ask(client, auth, workspace["id"], "What is a stack?")["session"]["id"]

    import uuid

    other = client.post("/api/auth/register", json={
        "email": f"other-{uuid.uuid4().hex[:8]}@example.com",
        "password": "correct-horse-battery"}).json()["access_token"]
    other_auth = {"Authorization": f"Bearer {other}"}

    # A different account must not read or extend another student's conversation.
    assert client.get(
        f"/api/workspaces/{workspace['id']}/assistant/sessions/{session_id}",
        headers=other_auth).status_code == 404
    assert client.get(
        f"/api/workspaces/{workspace['id']}/assistant/sessions",
        headers=other_auth).status_code == 404
    assert client.post(
        f"/api/workspaces/{workspace['id']}/assistant/ask",
        json={"message": "hi"}, headers=other_auth).status_code == 404
    assert client.delete(
        f"/api/workspaces/{workspace['id']}/assistant/sessions/{session_id}",
        headers=other_auth).status_code == 404


def test_session_from_another_workspace_is_rejected(client, auth):
    first = _workspace(client, auth, "Algorithms")
    second = _workspace(client, auth, "Databases")
    _upload(client, auth, first["id"], "a.txt", make_text_document())
    _upload(client, auth, second["id"], "d.txt", b"Normalisation reduces redundancy in a relation.")
    session_id = _ask(client, auth, first["id"], "What is a stack?")["session"]["id"]

    # Reusing a session id under a different workspace must not be allowed.
    response = client.post(f"/api/workspaces/{second['id']}/assistant/ask",
                           json={"message": "hi", "session_id": session_id}, headers=auth)
    assert response.status_code == 404
