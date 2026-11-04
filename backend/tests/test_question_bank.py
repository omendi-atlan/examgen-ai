"""Question-bank API tests for provenance, privacy, approval and blueprint generation."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from app.api.routes.question_bank import get_question_generation_service
from app.core.config import Settings
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    AcademicDocument,
    DocumentExtraction,
    DocumentTextSegment,
    DocumentVersion,
    ExtractionStatus,
    MembershipRole,
    MembershipStatus,
    Subject,
    User,
    WorkspaceMembership,
)
from app.schemas.question_bank import QuestionContentInput
from app.services.question_generation import (
    QuestionGenerationError,
    QuestionGenerationService,
    validate_generated_set,
)

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine_for_tests()
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


def create_engine_for_tests():
    return create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def create_context(client: TestClient, label: str = "question-bank") -> dict:
    email = f"{uuid4()}@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Question author",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert registered.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9!"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    workspace = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Question Bank Workspace", "slug": f"{label}-{uuid4().hex[:10]}"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Information Systems"},
    )
    assert subject.status_code == 201
    topic = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject.json()['id']}/topics",
        headers=headers,
        json={"name": "Database Fundamentals"},
    )
    assert topic.status_code == 201
    outcome = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/topics/{topic.json()['id']}/learning-outcomes",
        headers=headers,
        json={"code": "LO-DB-01", "description": "Explain relational database keys and constraints."},
    )
    assert outcome.status_code == 201
    return {
        "headers": headers,
        "workspace_id": workspace_id,
        "subject_id": subject.json()["id"],
        "topic_id": topic.json()["id"],
        "outcome_id": outcome.json()["id"],
    }


def add_source(
    context: dict,
    *,
    visibility: str = "private",
    text: str = "A primary key uniquely identifies each row in a relational table.",
) -> tuple[UUID, UUID]:
    with Session(app.state.test_engine) as db:
        owner = db.scalar(
            select(User).where(
                User.id
                == db.scalar(
                    select(WorkspaceMembership.user_id).where(
                        WorkspaceMembership.workspace_id == UUID(context["workspace_id"])
                    )
                )
            )
        )
        assert owner is not None
        subject = db.get(Subject, UUID(context["subject_id"]))
        assert subject is not None
        document = AcademicDocument(
            workspace_id=UUID(context["workspace_id"]),
            subject_id=subject.id,
            visibility=visibility,
            title="Database lecture notes",
            created_by=owner.id,
            current_version_number=1,
        )
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            original_filename="database-notes.txt",
            storage_key=f"test/{uuid4().hex}",
            media_type="text/plain",
            file_extension=".txt",
            size_bytes=len(text.encode()),
            sha256=uuid4().hex + uuid4().hex[:32],
            uploaded_by=owner.id,
            provenance={"source_type": "lecture_notes"},
        )
        db.add(version)
        db.flush()
        extraction = DocumentExtraction(
            version_id=version.id,
            status=ExtractionStatus.EXTRACTED,
            parser_name="text",
            parser_version="1",
            page_count=1,
            character_count=len(text),
            extraction_metadata={},
            quality_report={"outcome": "usable"},
        )
        db.add(extraction)
        db.flush()
        segment = DocumentTextSegment(
            extraction_id=extraction.id,
            ordinal=1,
            locator="page:1",
            text=text,
            metadata_json={},
        )
        db.add(segment)
        db.commit()
        return version.id, segment.id


def question_payload(context: dict, segment_id: UUID, visibility: str = "private") -> dict:
    return {
        "subject_id": context["subject_id"],
        "topic_id": context["topic_id"],
        "learning_outcome_id": context["outcome_id"],
        "visibility": visibility,
        "content": {
            "question_type": "multiple_choice",
            "prompt": "Which database key uniquely identifies each row in a relational table?",
            "marks": 2,
            "cognitive_level": "remember",
            "difficulty": "easy",
            "response_schema": {
                "options": [
                    {"id": "A", "label": "Primary key"},
                    {"id": "B", "label": "Foreign key"},
                    {"id": "C", "label": "Composite index"},
                ]
            },
            "answer_key": {"correct_option_id": "A"},
            "model_answer": "The primary key uniquely identifies each row.",
            "explanation": "A primary key enforces row identity and uniqueness.",
            "source_segment_ids": [str(segment_id)],
        },
    }


def test_student_private_question_has_no_answer_key_and_isolated_from_other_students(
    client: TestClient,
) -> None:
    context = create_context(client, "private-question")
    with Session(app.state.test_engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == UUID(context["workspace_id"])
            )
        )
        assert membership is not None
        membership.role = MembershipRole.STUDENT
        db.commit()
    _, segment_id = add_source(context)
    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/questions",
        headers=context["headers"],
        json=question_payload(context, segment_id),
    )
    assert created.status_code == 201, created.text
    question = created.json()
    assert question["visibility"] == "private"
    denied_cohort = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/questions",
        headers=context["headers"],
        json=question_payload(context, segment_id, visibility="cohort"),
    )
    assert denied_cohort.status_code == 403
    assert question["versions"][0]["status"] == "draft"
    assert "answer_key" not in question["versions"][0]
    assert "model_answer" not in question["versions"][0]
    assert question["versions"][0]["citations"][0]["source_locator"] == "page:1"

    listed = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions",
        headers=context["headers"],
    )
    assert listed.status_code == 200
    assert question["id"] in [item["id"] for item in listed.json()]

    other_email = "question-bank-outsider@example.test"
    assert client.post(
        "/api/v1/auth/register",
        json={
            "email": other_email,
            "display_name": "Other student",
            "password": "Correct-Horse-Battery-9!",
        },
    ).status_code == 201
    other_login = client.post(
        "/api/v1/auth/login",
        json={"email": other_email, "password": "Correct-Horse-Battery-9!"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    with Session(app.state.test_engine) as db:
        other = db.scalar(select(User).where(User.email == other_email))
        assert other is not None
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(context["workspace_id"]),
                user_id=other.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    hidden = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{question['id']}",
        headers=other_headers,
    )
    assert hidden.status_code == 404
    forbidden = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{question['id']}/authoring",
        headers=context["headers"],
    )
    assert forbidden.status_code == 403


def test_staff_approved_cohort_question_is_visible_without_key(client: TestClient) -> None:
    context = create_context(client, "cohort-question")
    with Session(app.state.test_engine) as db:
        subject = db.get(Subject, UUID(context["subject_id"]))
        assert subject is not None
        subject.resource_sharing_enabled = True
        db.commit()
    _, segment_id = add_source(context, visibility="cohort")
    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/questions",
        headers=context["headers"],
        json=question_payload(context, segment_id, visibility="cohort"),
    )
    assert created.status_code == 201, created.text
    question = created.json()
    version_id = question["versions"][0]["id"]

    student_email = "question-cohort-student@example.test"
    assert client.post(
        "/api/v1/auth/register",
        json={
            "email": student_email,
            "display_name": "Cohort student",
            "password": "Correct-Horse-Battery-9!",
        },
    ).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": student_email, "password": "Correct-Horse-Battery-9!"},
    )
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with Session(app.state.test_engine) as db:
        student = db.scalar(select(User).where(User.email == student_email))
        assert student is not None
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(context["workspace_id"]),
                user_id=student.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    hidden_before_approval = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{question['id']}",
        headers=student_headers,
    )
    assert hidden_before_approval.status_code == 404

    approved = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{question['id']}"
        f"/versions/{version_id}/approve",
        headers=context["headers"],
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["versions"][0]["answer_key"]["correct_option_id"] == "A"

    visible = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{question['id']}",
        headers=student_headers,
    )
    assert visible.status_code == 200
    assert "answer_key" not in visible.json()["versions"][0]
    assert "model_answer" not in visible.json()["versions"][0]


def test_cohort_question_cannot_cite_private_student_resource(client: TestClient) -> None:
    context = create_context(client, "cohort-private-source")
    _, segment_id = add_source(context, visibility="private")
    rejected = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/questions",
        headers=context["headers"],
        json=question_payload(context, segment_id, visibility="cohort"),
    )
    assert rejected.status_code == 409


def test_question_generation_persists_blueprint_fit_and_source_provenance(
    client: TestClient,
) -> None:
    context = create_context(client, "question-generation")
    source_version_id, segment_id = add_source(context)
    blueprint_payload = {
        "subject_id": context["subject_id"],
        "title": "Database Fundamentals Practice Blueprint",
        "duration_minutes": 30,
        "total_marks": 2,
        "question_count": 1,
        "cognitive_distribution": {"remember": 100},
        "difficulty_distribution": {"easy": 100},
        "question_type_distribution": {"multiple_choice": 100},
        "topic_weights": [{"topic_id": context["topic_id"], "target_marks": 2}],
        "outcome_weights": [{"learning_outcome_id": context["outcome_id"], "target_marks": 2}],
    }
    blueprint = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=blueprint_payload,
    )
    assert blueprint.status_code == 201, blueprint.text
    blueprint_data = blueprint.json()
    blueprint_version = blueprint_data["versions"][0]
    approved = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint_data['id']}"
        f"/versions/{blueprint_version['id']}/approve",
        headers=context["headers"],
    )
    assert approved.status_code == 200, approved.text

    class FakeGenerator:
        async def generate(self, **kwargs):
            return [
                {
                    "topic_id": UUID(context["topic_id"]),
                    "learning_outcome_id": UUID(context["outcome_id"]),
                    "content": QuestionContentInput(
                        question_type="multiple_choice",
                        prompt="Which key uniquely identifies a row in a relational table?",
                        marks=2,
                        cognitive_level="remember",
                        difficulty="easy",
                        response_schema={
                            "options": [
                                {"id": "A", "label": "Primary key"},
                                {"id": "B", "label": "Foreign key"},
                            ]
                        },
                        answer_key={"correct_option_id": "A"},
                        model_answer="The primary key uniquely identifies a row.",
                        explanation="The primary key is unique for each row.",
                        source_segment_ids=[segment_id],
                    ),
                }
            ]

    app.dependency_overrides[get_question_generation_service] = lambda: FakeGenerator()
    try:
        generated = client.post(
            f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint_data['id']}"
            f"/versions/{blueprint_version['id']}/generate-questions",
            headers=context["headers"],
            json={"source_version_ids": [str(source_version_id)]},
        )
    finally:
        app.dependency_overrides.pop(get_question_generation_service, None)

    assert generated.status_code == 201, generated.text
    result = generated.json()
    assert result["generated_count"] == 1
    assert result["total_marks"] == 2
    generated_question = result["questions"][0]
    assert "answer_key" not in generated_question["versions"][0]
    assert generated_question["versions"][0]["citations"][0]["source_segment_id"] == str(segment_id)

    authoring = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/questions/{generated_question['id']}/authoring",
        headers=context["headers"],
    )
    assert authoring.status_code == 200
    assert authoring.json()["versions"][0]["answer_key"]["correct_option_id"] == "A"


def test_question_schema_rejects_wrong_key_and_rubric_total() -> None:
    with pytest.raises(ValueError):
        QuestionContentInput(
            question_type="multiple_choice",
            prompt="Select the primary key.",
            marks=2,
            cognitive_level="remember",
            difficulty="easy",
            response_schema={"options": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]},
            answer_key={"correct_option_id": "C"},
            source_segment_ids=[uuid4()],
        )
    with pytest.raises(ValueError):
        QuestionContentInput(
            question_type="short_answer",
            prompt="Explain primary keys.",
            marks=4,
            cognitive_level="understand",
            difficulty="medium",
            response_schema={},
            answer_key={"expected": "A unique identifier"},
            rubric={"criteria": [{"description": "Definition", "marks": 3}]},
            source_segment_ids=[uuid4()],
        )


@pytest.mark.anyio
async def test_question_generator_fails_closed_without_provider_credentials() -> None:
    service = QuestionGenerationService(Settings(openai_api_key=None))
    with pytest.raises(QuestionGenerationError) as error:
        await service.generate(
            blueprint_version=SimpleNamespace(),
            subject_name="Database Fundamentals",
            topic_context=[],
            outcome_context=[],
            source_segments=[],
        )
    assert error.value.status_code == 503


def generated_item(topic_id: UUID, outcome_id: UUID, segment_id: UUID) -> dict:
    return {
        "topic_id": str(topic_id),
        "learning_outcome_id": str(outcome_id),
        "question_type": "multiple_choice",
        "prompt": "Which key uniquely identifies each row in a relational table?",
        "marks": 2,
        "cognitive_level": "remember",
        "difficulty": "easy",
        "response_schema": {
            "options": [
                {"id": "A", "label": "Primary key"},
                {"id": "B", "label": "Foreign key"},
            ]
        },
        "answer_key": {"correct_option_id": "A"},
        "model_answer": "The primary key uniquely identifies a row.",
        "explanation": "A primary key uniquely identifies each row.",
        "source_segment_ids": [str(segment_id)],
    }


def blueprint_for_generation(topic_id: UUID, outcome_id: UUID):
    return SimpleNamespace(
        title="Database fundamentals",
        question_count=1,
        total_marks=2,
        cognitive_distribution={"remember": 100},
        difficulty_distribution={"easy": 100},
        question_type_distribution={"multiple_choice": 100},
        topic_weights=[SimpleNamespace(topic_id=topic_id, target_marks=2)],
        outcome_weights=[SimpleNamespace(learning_outcome_id=outcome_id, target_marks=2)],
    )


def test_generation_validation_enforces_exact_blueprint_and_source_coverage() -> None:
    topic_id = uuid4()
    outcome_id = uuid4()
    segment_id = uuid4()
    blueprint = blueprint_for_generation(topic_id, outcome_id)
    validated = validate_generated_set(
        raw={"questions": [generated_item(topic_id, outcome_id, segment_id)]},
        blueprint_version=blueprint,
        available_segment_ids={segment_id},
    )
    assert len(validated) == 1
    assert validated[0]["content"].marks == 2

    invalid = generated_item(topic_id, outcome_id, segment_id)
    invalid["marks"] = 1
    with pytest.raises(QuestionGenerationError) as error:
        validate_generated_set(
            raw={"questions": [invalid]},
            blueprint_version=blueprint,
            available_segment_ids={segment_id},
        )
    assert error.value.status_code == 422

    invalid_source = generated_item(topic_id, outcome_id, uuid4())
    with pytest.raises(QuestionGenerationError) as error:
        validate_generated_set(
            raw={"questions": [invalid_source]},
            blueprint_version=blueprint,
            available_segment_ids={segment_id},
        )
    assert error.value.status_code == 422


@pytest.mark.anyio
async def test_openai_adapter_uses_server_secret_and_validates_structured_response() -> None:
    topic_id = uuid4()
    outcome_id = uuid4()
    segment_id = uuid4()
    blueprint = blueprint_for_generation(topic_id, outcome_id)
    calls = []

    def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "api.openai.com"
        assert request.headers["Authorization"] == "Bearer test-provider-secret"
        payload = __import__("json").loads(request.content)
        assert "untrusted academic data" in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": __import__("json").dumps(
                                {"questions": [generated_item(topic_id, outcome_id, segment_id)]}
                            )
                        }
                    }
                ]
            },
        )

    service = QuestionGenerationService(
        Settings(openai_api_key=SecretStr("test-provider-secret")),
        transport=httpx.MockTransport(provider),
    )
    result = await service.generate(
        blueprint_version=blueprint,
        subject_name="Information Systems",
        topic_context=[{"id": str(topic_id), "name": "Database Fundamentals"}],
        outcome_context=[{"id": str(outcome_id), "code": "LO-DB-01", "description": "Explain keys."}],
        source_segments=[{"id": str(segment_id), "locator": "page:1", "text": "Primary keys uniquely identify rows."}],
    )
    assert len(calls) == 1
    assert len(result) == 1
    assert result[0]["content"].question_type == "multiple_choice"
