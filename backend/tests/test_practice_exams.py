"""Practice exam snapshots, timed attempts, autosave and objective marking tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    PracticeAttempt,
    Question,
    QuestionReviewStatus,
    QuestionVersion,
    User,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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


def create_question_context(client: TestClient) -> dict:
    email = "practice-student@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Practice student",
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
        json={"name": "Practice Workspace", "slug": f"practice-{uuid4().hex[:12]}"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Algorithms"},
    )
    assert subject.status_code == 201
    subject_id = subject.json()["id"]

    with Session(app.state.test_engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        items = [
            {
                "question_type": "multiple_choice",
                "stem": "Which data structure follows the first-in, first-out principle?",
                "options": [
                    {"id": "A", "text": "Queue"},
                    {"id": "B", "text": "Stack"},
                    {"id": "C", "text": "Tree"},
                ],
                "correct_answer": {"option_id": "A"},
                "explanation": "A queue processes the earliest inserted item first.",
                "marks": 2,
                "difficulty": "easy",
                "cognitive_level": "remember",
            },
            {
                "question_type": "short_answer",
                "stem": "Explain why binary search requires sorted input.",
                "options": None,
                "correct_answer": {
                    "key_points": ["The midpoint comparison eliminates one half of the search space."],
                    "sample_answer": "Sorted order makes it possible to discard half the remaining values after each comparison.",
                },
                "explanation": "The ordering allows the algorithm to choose the half that may contain the target.",
                "marks": 3,
                "difficulty": "medium",
                "cognitive_level": "understand",
            },
        ]
        version_ids = []
        for index, item in enumerate(items):
            question = Question(
                workspace_id=UUID(workspace_id),
                subject_id=UUID(subject_id),
                created_by=user.id,
                current_version_number=1,
                fingerprint=f"practice-test-{index}-{uuid4().hex}",
            )
            db.add(question)
            db.flush()
            version = QuestionVersion(
                question_id=question.id,
                version_number=1,
                question_type=item["question_type"],
                stem=item["stem"],
                options=item["options"],
                correct_answer=item["correct_answer"],
                explanation=item["explanation"],
                marks=item["marks"],
                difficulty=item["difficulty"],
                cognitive_level=item["cognitive_level"],
                source_citations=[],
                generation_model="test-fixture",
                prompt_version="test",
                review_status=QuestionReviewStatus.DRAFT,
            )
            db.add(version)
            db.flush()
            version_ids.append(str(version.id))
        db.commit()
    return {
        "headers": headers,
        "workspace_id": workspace_id,
        "subject_id": subject_id,
        "question_version_ids": version_ids,
    }


def create_exam(client: TestClient, context: dict) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}/practice-exams",
        headers=context["headers"],
        json={
            "title": "Algorithms practice",
            "duration_minutes": 30,
            "question_version_ids": context["question_version_ids"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_practice_attempt_hides_answer_keys_until_submission_and_marks_objective_items(
    client: TestClient,
) -> None:
    context = create_question_context(client)
    exam = create_exam(client, context)
    assert exam["question_count"] == 2
    assert exam["total_marks"] == 5

    started = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-exams/{exam['id']}/attempts",
        headers=context["headers"],
    )
    assert started.status_code == 201, started.text
    attempt = started.json()
    assert attempt["status"] == "in_progress"
    assert len(attempt["questions"]) == 2
    assert "correct_answer" not in started.text
    assert "explanation" not in started.text

    mcq = attempt["questions"][0]
    written = attempt["questions"][1]
    saved = client.put(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-attempts/{attempt['id']}/responses/{mcq['exam_question_id']}",
        headers=context["headers"],
        json={"response": {"option_id": "A"}},
    )
    assert saved.status_code == 200, saved.text
    assert "correct_answer" not in saved.text

    saved_written = client.put(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-attempts/{attempt['id']}/responses/{written['exam_question_id']}",
        headers=context["headers"],
        json={"response": {"text": "The midpoint comparison removes half of the remaining search space."}},
    )
    assert saved_written.status_code == 200

    submitted = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-attempts/{attempt['id']}/submit",
        headers=context["headers"],
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["awarded_marks"] == 2
    assert result["total_marks"] == 5
    assert result["pending_review_count"] == 1
    assert result["questions"][0]["is_correct"] is True
    assert result["questions"][0]["awarded_marks"] == 2
    assert result["questions"][0]["correct_answer"] == {"option_id": "A"}
    assert result["questions"][0]["explanation"]
    assert result["questions"][1]["marking_status"] == "pending_review"
    assert result["questions"][1]["correct_answer"]["key_points"]

    repeated = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-attempts/{attempt['id']}/submit",
        headers=context["headers"],
    )
    assert repeated.status_code == 200
    assert repeated.json()["awarded_marks"] == 2


def test_attempt_expiry_is_enforced_by_server_clock_and_finalises_saved_responses(
    client: TestClient,
) -> None:
    context = create_question_context(client)
    exam = create_exam(client, context)
    started = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-exams/{exam['id']}/attempts",
        headers=context["headers"],
    )
    assert started.status_code == 201
    attempt_id = started.json()["id"]
    with Session(app.state.test_engine) as db:
        attempt = db.scalar(select(PracticeAttempt).where(PracticeAttempt.id == UUID(attempt_id)))
        assert attempt is not None
        attempt.expires_at = datetime.now(UTC) - timedelta(seconds=2)
        db.commit()

    expired = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-attempts/{attempt_id}",
        headers=context["headers"],
    )
    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert expired.json()["submitted_at"] is not None
    assert "correct_answer" in expired.text


def test_student_cannot_start_or_read_another_students_practice_exam(
    client: TestClient,
) -> None:
    context = create_question_context(client)
    exam = create_exam(client, context)
    outsider_email = "practice-outsider@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": outsider_email,
            "display_name": "Practice outsider",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": outsider_email, "password": "Correct-Horse-Battery-9!"},
    )
    assert login.status_code == 200
    outsider_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with Session(app.state.test_engine) as db:
        outsider = db.scalar(select(User).where(User.email == outsider_email))
        assert outsider is not None
        from app.models import MembershipRole, MembershipStatus, WorkspaceMembership

        db.add(
            WorkspaceMembership(
                workspace_id=UUID(context["workspace_id"]),
                user_id=outsider.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    denied = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/subjects/{context['subject_id']}"
        f"/practice-exams/{exam['id']}/attempts",
        headers=outsider_headers,
    )
    assert denied.status_code == 404
