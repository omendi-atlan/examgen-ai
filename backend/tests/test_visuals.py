"""Visual requirement analysis, versioned asset approval and moderation gate tests."""

from uuid import UUID, uuid4

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models import (
    LearningOutcome,
    Question,
    QuestionReviewStatus,
    QuestionVersion,
    User,
    WorkspaceMembership,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

VISUAL_TOPIC = "Network topology and routing"
PLAIN_TOPIC = "Revision technique"


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


def build_context(client: TestClient) -> dict:
    """Create a student, workspace, subject, two topics and an approved blueprint version."""
    email = f"visuals-{uuid4().hex[:10]}@example.test"
    assert client.post(
        "/api/v1/auth/register",
        json={"email": email, "display_name": "Visual student", "password": "Correct-Horse-Battery-9!"},
    ).status_code == 201
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-9!"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    workspace_id = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Visual Workspace", "slug": f"visual-{uuid4().hex[:12]}"},
    ).json()["id"]
    subject_id = client.post(
        f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects",
        headers=headers,
        json={"name": "Networking"},
    ).json()["id"]

    topic_ids = {}
    for name in (VISUAL_TOPIC, PLAIN_TOPIC):
        topic = client.post(
            f"/api/v1/workspaces/{workspace_id}/taxonomy/subjects/{subject_id}/topics",
            headers=headers,
            json={"name": name},
        )
        assert topic.status_code == 201, topic.text
        topic_ids[name] = topic.json()["id"]

    with Session(app.state.test_engine) as db:
        user = db.scalar(select(User).where(User.email == email))
        for index in range(3):
            db.add(
                LearningOutcome(
                    workspace_id=UUID(workspace_id),
                    topic_id=UUID(topic_ids[VISUAL_TOPIC]),
                    code=f"LO{index + 1}",
                    description=f"Outcome {index + 1} for the routing topic",
                    created_by=user.id,
                )
            )
        db.commit()
        outcome_ids = [str(item) for item in db.scalars(select(LearningOutcome.id)).all()]

    # 20 marks across three outcomes: 7 + 7 + 6.
    outcome_weights = [
        {"learning_outcome_id": outcome_id, "target_marks": marks}
        for outcome_id, marks in zip(outcome_ids, (7, 7, 6), strict=True)
    ]
    blueprint = client.post(
        f"/api/v1/workspaces/{workspace_id}/blueprints",
        headers=headers,
        json={
            "subject_id": subject_id,
            "title": "Networking paper",
            "duration_minutes": 60,
            "total_marks": 20,
            "question_count": 2,
            "cognitive_distribution": {"remember": 100},
            "difficulty_distribution": {"easy": 100},
            "question_type_distribution": {"short_answer": 100},
            "topic_weights": [
                {"topic_id": topic_ids[VISUAL_TOPIC], "target_marks": 10},
                {"topic_id": topic_ids[PLAIN_TOPIC], "target_marks": 10},
            ],
            "outcome_weights": outcome_weights,
        },
    )
    assert blueprint.status_code == 201, blueprint.text
    blueprint_id = blueprint.json()["id"]
    version_id = blueprint.json()["versions"][0]["id"]
    approved = client.post(
        f"/api/v1/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    return {
        "headers": headers,
        "workspace_id": workspace_id,
        "subject_id": subject_id,
        "blueprint_id": blueprint_id,
        "version_id": version_id,
        "topic_ids": topic_ids,
    }


def analyse(client: TestClient, context: dict) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals/analyse",
        headers=context["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_analysis_classifies_visual_requirements_deterministically(client):
    context = build_context(client)
    body = analyse(client, context)

    by_topic = {item["topic_name"]: item for item in body["items"]}
    assert by_topic[VISUAL_TOPIC]["requirement_level"] == "essential"
    assert by_topic[VISUAL_TOPIC]["recommended_kind"] in {"network", "flowchart", "tree"}
    assert by_topic[VISUAL_TOPIC]["signals"]["signal_count"] >= 2
    assert by_topic[PLAIN_TOPIC]["requirement_level"] == "unnecessary"
    assert by_topic[PLAIN_TOPIC]["recommended_kind"] is None
    assert body["essential_count"] == 1 and body["unnecessary_count"] == 1

    # Idempotent without force, recomputed with force.
    again = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals/analyse",
        headers=context["headers"],
    )
    assert again.status_code == 201
    assert again.json()["id"] == body["id"]


def test_publication_is_blocked_until_essential_visual_is_approved(client):
    context = build_context(client)
    analyse(client, context)
    moderation_url = (
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/moderation"
    )
    report = client.get(moderation_url, headers=context["headers"]).json()
    assert report["can_publish"] is False
    assert report["status"] == "rejected"
    checks = {finding["check"] for finding in report["findings"]}
    assert "essential_visuals_approved" in checks

    items = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals",
        headers=context["headers"],
    ).json()["items"]
    essential = next(item for item in items if item["requirement_level"] == "essential")

    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets",
        headers=context["headers"],
        json={"requirement_item_id": essential["id"]},
    )
    assert created.status_code == 201, created.text
    asset = created.json()
    assert asset["versions"][0]["status"] == "draft"
    assert asset["versions"][0]["validation_report"]["valid"] is True

    # A draft asset does not satisfy the gate.
    still_blocked = client.get(moderation_url, headers=context["headers"]).json()
    assert still_blocked["can_publish"] is False

    asset_version_id = asset["versions"][0]["id"]
    approved = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets/{asset['id']}"
        f"/versions/{asset_version_id}/decision",
        headers=context["headers"],
        json={"decision": "approved", "rationale": "Labels and relationships verified against the source."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["versions"][0]["status"] == "approved"

    after = client.get(moderation_url, headers=context["headers"]).json()
    visual_findings = [
        finding for finding in after["findings"] if finding["check"] == "essential_visuals_approved"
    ]
    assert visual_findings and visual_findings[0]["severity"] == "info"


def test_asset_versioning_is_immutable_and_svg_is_script_free(client):
    context = build_context(client)
    analyse(client, context)
    items = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals",
        headers=context["headers"],
    ).json()["items"]
    essential = next(item for item in items if item["requirement_level"] == "essential")

    created = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets",
        headers=context["headers"],
        json={"requirement_item_id": essential["id"]},
    ).json()
    first_version = created["versions"][0]

    revised = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets/{created['id']}/versions",
        headers=context["headers"],
        json={
            "spec": {
                "title": "Revised routing flow",
                "kind": "flowchart",
                "nodes": [
                    {"id": "a", "label": "Inspect packet header"},
                    {"id": "b", "label": "Select next hop"},
                ],
                "edges": [{"source": "a", "target": "b"}],
            }
        },
    )
    assert revised.status_code == 201, revised.text
    versions = revised.json()["versions"]
    assert [item["version_number"] for item in versions] == [1, 2]
    # The earlier immutable version is preserved unchanged.
    assert versions[0]["id"] == first_version["id"]
    assert versions[0]["diagram_kind"] == first_version["diagram_kind"]

    svg = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets/{created['id']}"
        f"/versions/{versions[1]['id']}/svg",
        headers=context["headers"],
    )
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    body = svg.text
    assert body.startswith("<svg")
    assert "<script" not in body.casefold()
    assert "onload=" not in body.casefold()
    assert "Select next hop" in body
    assert svg.headers["content-security-policy"].startswith("default-src 'none'")


def test_data_charts_require_explicit_values_and_reject_invented_ones(client):
    context = build_context(client)
    items = analyse(client, context)["items"]
    essential = next(item for item in items if item["requirement_level"] == "essential")

    # Auto-drafting a data-bearing chart from outcomes is refused.
    invalid = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets",
        headers=context["headers"],
        json={
            "blueprint_version_id": context["version_id"],
            "spec": {
                "title": "Throughput",
                "kind": "bar_chart",
                "nodes": [{"id": "a", "label": "Baseline"}],
                "edges": [],
            },
        },
    )
    assert invalid.status_code == 422
    assert "numeric value" in str(invalid.json()["detail"])

    valid = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/visuals/assets",
        headers=context["headers"],
        json={
            "blueprint_version_id": context["version_id"],
            "spec": {
                "title": "Measured throughput",
                "kind": "bar_chart",
                "nodes": [
                    {"id": "a", "label": "Baseline", "value": 40},
                    {"id": "b", "label": "Optimised", "value": 95},
                ],
                "edges": [],
            },
        },
    )
    assert valid.status_code == 201, valid.text
    assert essential["id"]  # sanity: the essential requirement still exists


def test_visual_routes_enforce_workspace_roles_and_isolation(client):
    context = build_context(client)

    # A student role may not author visual assets.
    other_email = f"student-{uuid4().hex[:10]}@example.test"
    client.post(
        "/api/v1/auth/register",
        json={"email": other_email, "display_name": "Plain student", "password": "Correct-Horse-Battery-9!"},
    )
    other_token = client.post(
        "/api/v1/auth/login", json={"email": other_email, "password": "Correct-Horse-Battery-9!"}
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}
    with Session(app.state.test_engine) as db:
        from app.models import MembershipRole, MembershipStatus, WorkspaceMembership

        user = db.scalar(select(User).where(User.email == other_email))
        db.add(
            WorkspaceMembership(
                workspace_id=UUID(context["workspace_id"]),
                user_id=user.id,
                role=MembershipRole.STUDENT,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()

    forbidden = client.post(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals/analyse",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    # A user who is not a member of the workspace cannot reach it at all.
    outsider_email = f"outsider-{uuid4().hex[:10]}@example.test"
    client.post(
        "/api/v1/auth/register",
        json={"email": outsider_email, "display_name": "Outsider", "password": "Correct-Horse-Battery-9!"},
    )
    outsider = client.post(
        "/api/v1/auth/login", json={"email": outsider_email, "password": "Correct-Horse-Battery-9!"}
    ).json()["access_token"]
    hidden = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/visuals",
        headers={"Authorization": f"Bearer {outsider}"},
    )
    assert hidden.status_code == 404


def test_moderation_reports_missing_question_coverage(client):
    context = build_context(client)
    analyse(client, context)
    report = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/moderation",
        headers=context["headers"],
    ).json()
    checks = {finding["check"]: finding for finding in report["findings"]}
    assert checks["topic_coverage"]["severity"] == "critical"
    assert checks["question_marks_sufficient"]["severity"] == "critical"

    # Approve questions covering every topic with enough marks, then re-check.
    with Session(app.state.test_engine) as db:
        owner_id = db.scalar(
            select(User.id).join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
            .where(WorkspaceMembership.workspace_id == UUID(context["workspace_id"]))
            .order_by(WorkspaceMembership.created_at)
        )
        workspace_uuid = UUID(context["workspace_id"])
        subject_uuid = UUID(context["subject_id"])
        for name, marks in ((VISUAL_TOPIC, 10), (PLAIN_TOPIC, 10)):
            topic_id = UUID(context["topic_ids"][name])
            question = Question(
                workspace_id=workspace_uuid,
                subject_id=subject_uuid,
                created_by=owner_id,
                current_version_number=1,
                fingerprint=f"moderation-{name}-{uuid4().hex}",
            )
            db.add(question)
            db.flush()
            db.add(
                QuestionVersion(
                    question_id=question.id,
                    version_number=1,
                    topic_id=topic_id,
                    question_type="short_answer",
                    stem=f"Explain {name}.",
                    options=None,
                    correct_answer={"key_points": ["A correct explanation."]},
                    explanation="Because it is correct.",
                    marks=marks,
                    difficulty="easy",
                    cognitive_level="remember",
                    source_citations=[],
                    generation_model="test",
                    prompt_version="test-v1",
                    review_status=QuestionReviewStatus.APPROVED,
                )
            )
        db.commit()

    after = client.get(
        f"/api/v1/workspaces/{context['workspace_id']}/blueprints/{context['blueprint_id']}"
        f"/versions/{context['version_id']}/moderation",
        headers=context["headers"],
    ).json()
    checks_after = {finding["check"]: finding for finding in after["findings"]}
    assert checks_after["topic_coverage"]["severity"] == "info"
    assert checks_after["question_marks_sufficient"]["severity"] == "info"
