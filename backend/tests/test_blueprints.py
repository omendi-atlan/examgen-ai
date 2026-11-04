"""Blueprint API tests for constraints, immutable versions and moderator approval."""

from uuid import UUID, uuid4

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models import AuditEvent
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


def create_workspace_and_taxonomy(client: TestClient, label: str = "blueprint") -> dict:
    email = f"{uuid4()}@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Blueprint examiner",
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
        json={"name": "Blueprint Workspace", "slug": f"{label}-{uuid4().hex[:10]}"},
    )
    assert workspace.status_code == 201
    workspace_id = workspace.json()["id"]
    subject = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Software Engineering"},
    )
    assert subject.status_code == 201
    topics = []
    outcomes = []
    for name in ("Requirements Engineering", "Software Testing"):
        topic = client.post(
            f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject.json()['id']}/topics",
            headers=headers,
            json={"name": name},
        )
        assert topic.status_code == 201
        topics.append(topic.json()["id"])
        outcome = client.post(
            f"/api/v1/workspaces/{workspace_id}/taxonomy/topics/{topic.json()['id']}/learning-outcomes",
            headers=headers,
            json={"code": f"LO-{len(outcomes) + 1}", "description": f"Demonstrate {name.lower()} concepts."},
        )
        assert outcome.status_code == 201
        outcomes.append(outcome.json()["id"])
    return {
        "token": token,
        "headers": headers,
        "workspace_id": workspace_id,
        "subject_id": subject.json()["id"],
        "topic_ids": topics,
        "outcome_ids": outcomes,
    }


def blueprint_payload(context: dict, *, total_marks: int = 100, title: str = "Semester Exam") -> dict:
    first = total_marks // 2
    return {
        "subject_id": context["subject_id"],
        "title": title,
        "description": "Moderated assessment blueprint.",
        "duration_minutes": 120,
        "total_marks": total_marks,
        "question_count": 10,
        "cognitive_distribution": {
            "remember": 10,
            "understand": 20,
            "apply": 30,
            "analyze": 20,
            "evaluate": 10,
            "create": 10,
        },
        "difficulty_distribution": {"easy": 20, "medium": 60, "hard": 20},
        "question_type_distribution": {"multiple_choice": 40, "short_answer": 60},
        "outcome_weights": [
            {"learning_outcome_id": context["outcome_ids"][0], "target_marks": first},
            {"learning_outcome_id": context["outcome_ids"][1], "target_marks": total_marks - first},
        ],
        "topic_weights": [
            {"topic_id": context["topic_ids"][0], "target_marks": first},
            {"topic_id": context["topic_ids"][1], "target_marks": total_marks - first},
        ],
    }


def test_blueprint_create_append_and_approve_preserves_immutable_versions(
    client: TestClient,
) -> None:
    context = create_workspace_and_taxonomy(client)
    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=blueprint_payload(context),
    )
    assert created.status_code == 201
    blueprint = created.json()
    assert blueprint["current_version_number"] == 1
    first = blueprint["versions"][0]
    assert first["version_number"] == 1
    assert first["status"] == "draft"
    assert sum(item["target_marks"] for item in first["topic_weights"]) == 100
    assert sum(item["target_marks"] for item in first["outcome_weights"]) == 100

    appended = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint['id']}/versions",
        headers=context["headers"],
        json=blueprint_payload(context, total_marks=120, title="Revised Semester Exam"),
    )
    assert appended.status_code == 201
    revised = appended.json()
    assert revised["current_version_number"] == 2
    assert revised["versions"][0]["title"] == "Semester Exam"
    assert revised["versions"][0]["total_marks"] == 100
    second = revised["versions"][1]
    assert second["title"] == "Revised Semester Exam"
    assert second["total_marks"] == 120
    assert second["status"] == "draft"

    approved = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint['id']}"
        f"/versions/{second['id']}/approve",
        headers=context["headers"],
    )
    assert approved.status_code == 200
    approved_version = approved.json()["versions"][1]
    assert approved_version["status"] == "approved"
    assert approved_version["approved_by"] is not None
    assert approved_version["approved_at"] is not None

    repeated = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint['id']}"
        f"/versions/{second['id']}/approve",
        headers=context["headers"],
    )
    assert repeated.status_code == 409

    with Session(app.state.test_engine) as db:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.workspace_id == UUID(context["workspace_id"]),
                AuditEvent.action.in_(["exam_blueprint.created", "exam_blueprint.version_created", "exam_blueprint.version_approved"]),
            )
        ).all()
        assert len(events) == 4


def test_blueprint_rejects_invalid_percentages_and_mark_totals(client: TestClient) -> None:
    context = create_workspace_and_taxonomy(client, "invalid")
    payload = blueprint_payload(context)
    payload["cognitive_distribution"]["remember"] = 9
    invalid_percentages = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=payload,
    )
    assert invalid_percentages.status_code == 422

    payload = blueprint_payload(context)
    payload["topic_weights"][0]["target_marks"] = 49
    invalid_marks = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=payload,
    )
    assert invalid_marks.status_code == 422


def test_blueprint_rejects_topic_from_another_workspace(client: TestClient) -> None:
    owner = create_workspace_and_taxonomy(client, "owner")
    outsider = create_workspace_and_taxonomy(client, "outsider")
    payload = blueprint_payload(owner)
    payload["topic_weights"][0]["topic_id"] = outsider["topic_ids"][0]
    payload["outcome_weights"][0]["learning_outcome_id"] = outsider["outcome_ids"][0]

    rejected = client.post(
        f"/api/v1/workspaces/{owner['workspace_id']}/blueprints",
        headers=owner["headers"],
        json=payload,
    )
    assert rejected.status_code == 422


def test_blueprint_is_workspace_isolated_and_students_cannot_approve(client: TestClient) -> None:
    from app.models import MembershipRole, WorkspaceMembership

    context = create_workspace_and_taxonomy(client, "roles")
    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=blueprint_payload(context),
    )
    blueprint = created.json()
    version = blueprint["versions"][0]

    outsider = create_workspace_and_taxonomy(client, "reader")
    hidden = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint['id']}",
        headers=outsider["headers"],
    )
    assert hidden.status_code == 404

    with Session(app.state.test_engine) as db:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == context["workspace_id"]
            )
        )
        assert membership is not None
        membership.role = MembershipRole.STUDENT
        db.commit()

    forbidden = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{blueprint['id']}"
        f"/versions/{version['id']}/approve",
        headers=context["headers"],
    )
    assert forbidden.status_code == 403


def test_blueprint_rejects_incomplete_learning_outcome_mark_coverage(
    client: TestClient,
) -> None:
    context = create_workspace_and_taxonomy(client, "outcome-coverage")
    payload = blueprint_payload(context)
    payload["outcome_weights"][0]["target_marks"] = 49
    rejected = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints",
        headers=context["headers"],
        json=payload,
    )
    assert rejected.status_code == 422
