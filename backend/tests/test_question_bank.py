"""Source-grounded question generation, privacy and answer-key protection tests."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    DocumentExtraction,
    DocumentTextSegment,
    ExtractionStatus,
    MembershipRole,
    MembershipStatus,
    Question,
    QuestionVersion,
    User,
    WorkspaceMembership,
)
from app.schemas.questions import GeneratedQuestionEnvelope
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app.state.test_engine = engine

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.state.test_engine = None
    Base.metadata.drop_all(engine)
    engine.dispose()


def create_source(client: TestClient, email: str = "question-owner@example.test") -> dict:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Question author",
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
    headers = {"Authorization": f"Bearer {token}"}
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Question Workspace", "slug": f"question-{uuid4().hex[:12]}"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Database Systems"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/subjects/{subject_id}/resources",
        headers=headers,
        data={"title": "Relational database lecture notes"},
        files={
            "file": (
                "database-notes.txt",
                b"Relational databases organise data into tables. A primary key uniquely identifies each row. Foreign keys reference keys in related tables.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    resource = uploaded.json()
    version_id = resource["versions"][0]["id"]
    with Session(app.state.test_engine) as db:
        extraction = db.scalar(
            select(DocumentExtraction).where(DocumentExtraction.version_id == UUID(version_id))
        )
        assert extraction is not None
        extraction.status = ExtractionStatus.EXTRACTED
        extraction.character_count = 138
        db.add(
            DocumentTextSegment(
                extraction_id=extraction.id,
                ordinal=1,
                locator="page:1",
                text="Relational databases organise data into tables. A primary key uniquely identifies each row. Foreign keys reference keys in related tables.",
                metadata_json={},
            )
        )
        db.commit()
    return {
        "token": token,
        "headers": headers,
        "workspace_id": workspace_id,
        "subject_id": subject_id,
        "version_id": version_id,
        "resource_id": resource["id"],
    }


def fake_generation(source_segment_id: UUID) -> GeneratedQuestionEnvelope:
    return GeneratedQuestionEnvelope(
        questions=[
            {
                "question_type": "multiple_choice",
                "stem": "Which statement best describes a primary key in a relational table?",
                "options": [
                    {"id": "A", "text": "It uniquely identifies each row."},
                    {"id": "B", "text": "It stores duplicate rows."},
                    {"id": "C", "text": "It removes all foreign keys."},
                    {"id": "D", "text": "It encrypts the table."},
                ],
                "correct_answer": {"option_id": "A"},
                "explanation": "A primary key uniquely identifies each row in a relational table.",
                "marks": 2,
                "difficulty": "medium",
                "cognitive_level": "apply",
                "source_segment_ids": [source_segment_id],
            },
            {
                "question_type": "short_answer",
                "stem": "Explain how a foreign key supports relationships between relational tables.",
                "options": None,
                "correct_answer": {
                    "key_points": ["References a key in a related table."],
                    "sample_answer": "A foreign key references a key in another table to establish a relationship.",
                },
                "explanation": "Foreign keys provide references between related tables.",
                "marks": 3,
                "difficulty": "medium",
                "cognitive_level": "analyze",
                "source_segment_ids": [source_segment_id],
            },
        ]
    )


def test_question_generation_persists_source_cited_private_questions_without_answer_leaks(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import question_bank

    context = create_source(client)
    with Session(app.state.test_engine) as db:
        segment = db.scalar(select(DocumentTextSegment))
        assert segment is not None
        segment_id = segment.id

    monkeypatch.setattr(
        question_bank,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=SecretStr("test-secret-key"),
            openai_model="test-model",
            question_generation_timeout_seconds=30,
        ),
    )

    async def fake_provider(**_kwargs):
        return fake_generation(segment_id)

    monkeypatch.setattr(question_bank, "generate_question_payload", fake_provider)

    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/questions/generate",
        headers=context["headers"],
        json={
            "source_version_ids": [context["version_id"]],
            "question_count": 2,
            "total_marks": 5,
            "question_types": ["multiple_choice", "short_answer"],
            "difficulty": "medium",
            "cognitive_levels": ["apply", "analyze"],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["created_count"] == 2
    assert payload["total_marks"] == 5
    assert len(payload["questions"]) == 2
    first_version = payload["questions"][0]["versions"][0]
    assert first_version["question_type"] == "multiple_choice"
    assert first_version["source_citations"][0]["locator"] == "page:1"
    assert first_version["review_status"] == "draft"
    assert "correct_answer" not in first_version
    assert "explanation" not in first_version
    assert "correct_answer" not in response.text
    assert "sample_answer" not in response.text

    with Session(app.state.test_engine) as db:
        assert db.scalar(select(func.count(Question.id))) == 2
        stored = db.scalars(select(QuestionVersion).order_by(QuestionVersion.created_at)).all()
        assert len(stored) == 2
        assert stored[0].correct_answer == {"option_id": "A"}
        assert stored[0].generation_model == "test-model"
        assert stored[0].source_citations[0]["source_version_id"] == context["version_id"]

    duplicate = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/questions/generate",
        headers=context["headers"],
        json={
            "source_version_ids": [context["version_id"]],
            "question_count": 2,
            "total_marks": 5,
            "question_types": ["multiple_choice", "short_answer"],
            "difficulty": "medium",
            "cognitive_levels": ["apply", "analyze"],
        },
    )
    assert duplicate.status_code == 409
    with Session(app.state.test_engine) as db:
        assert db.scalar(select(func.count(Question.id))) == 2


def test_question_generation_rejects_unowned_private_sources(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import question_bank

    monkeypatch.setattr(
        question_bank,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=SecretStr("test-secret-key"),
            openai_model="test-model",
            question_generation_timeout_seconds=30,
        ),
    )
    context = create_source(client, "question-source-owner@example.test")
    outsider = create_source(client, "question-outsider@example.test")
    with Session(app.state.test_engine) as db:
        outsider_user = db.scalar(select(User).where(User.email == "question-outsider@example.test"))
        assert outsider_user is not None
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(context["workspace_id"]),
                user_id=outsider_user.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/questions/generate",
        headers=outsider["headers"],
        json={
            "source_version_ids": [context["version_id"]],
            "question_count": 2,
            "total_marks": 5,
            "question_types": ["multiple_choice", "short_answer"],
            "difficulty": "medium",
            "cognitive_levels": ["apply", "analyze"],
        },
    )
    assert response.status_code == 404
    with Session(app.state.test_engine) as db:
        assert db.scalar(select(func.count(Question.id))) == 0


def test_question_generation_fails_closed_when_provider_is_not_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import question_bank

    context = create_source(client)
    monkeypatch.setattr(
        question_bank,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=None,
            openai_model="test-model",
            question_generation_timeout_seconds=30,
        ),
    )
    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/questions/generate",
        headers=context["headers"],
        json={
            "source_version_ids": [context["version_id"]],
            "question_count": 2,
            "total_marks": 5,
        },
    )
    assert response.status_code == 503


def test_question_generation_rejects_provider_citations_not_in_uploaded_sources(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import question_bank

    context = create_source(client)
    monkeypatch.setattr(
        question_bank,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=SecretStr("test-secret-key"),
            openai_model="test-model",
            question_generation_timeout_seconds=30,
        ),
    )

    async def fake_provider(**_kwargs):
        return fake_generation(uuid4())

    monkeypatch.setattr(question_bank, "generate_question_payload", fake_provider)
    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/questions/generate",
        headers=context["headers"],
        json={
            "source_version_ids": [context["version_id"]],
            "question_count": 2,
            "total_marks": 5,
            "question_types": ["multiple_choice", "short_answer"],
            "difficulty": "medium",
            "cognitive_levels": ["apply", "analyze"],
        },
    )
    assert response.status_code == 422
    with Session(app.state.test_engine) as db:
        assert db.scalar(select(func.count(Question.id))) == 0
