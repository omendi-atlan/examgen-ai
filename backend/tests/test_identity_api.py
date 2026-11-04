"""End-to-end tests for identity, workspace isolation and audit persistence."""

import pytest
from app.core.database import Base, get_db
from app.main import app
from app.models import AuditEvent, MembershipRole, WorkspaceMembership
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
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": "Test User",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Correct-Horse-Battery-9!"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_registration_login_and_current_user(client: TestClient) -> None:
    user = register(client, " Learner@Example.test ")
    assert user["email"] == "learner@example.test"
    assert "password" not in user
    assert "password_hash" not in user

    token = login(client, "learner@example.test")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == user["id"]


def test_duplicate_registration_and_invalid_login_are_rejected(
    client: TestClient,
) -> None:
    register(client, "learner@example.test")
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "LEARNER@example.test",
            "display_name": "Duplicate",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert duplicate.status_code == 409

    invalid = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.test", "password": "incorrect"},
    )
    assert invalid.status_code == 401


def test_workspace_creation_assigns_owner_and_records_audit(client: TestClient) -> None:
    register(client, "owner@example.test")
    token = login(client, "owner@example.test")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Campus Exams", "slug": "campus-exams"},
    )
    assert response.status_code == 201
    workspace = response.json()

    listing = client.get("/api/v1/workspaces", headers=headers)
    assert [item["id"] for item in listing.json()] == [workspace["id"]]

    with Session(app.state.test_engine) as session:
        membership = session.scalar(select(WorkspaceMembership))
        assert membership is not None
        assert membership.role == MembershipRole.OWNER
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "workspace.created")
        )
        assert audit is not None


def test_workspace_isolation_hides_another_users_tenant(client: TestClient) -> None:
    register(client, "owner@example.test")
    owner_token = login(client, "owner@example.test")
    created = client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Private Workspace", "slug": "private-workspace"},
    )
    workspace_id = created.json()["id"]

    register(client, "outsider@example.test")
    outsider_token = login(client, "outsider@example.test")
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert response.status_code == 404


def test_workspace_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/workspaces").status_code == 401
    assert client.post(
        "/api/v1/workspaces",
        json={"name": "No Access", "slug": "no-access"},
    ).status_code == 401


def test_login_rate_limit_is_enforced_and_returns_retry_after(client: TestClient) -> None:
    register(client, "limited@example.test")
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "limited@example.test", "password": "incorrect"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "limited@example.test", "password": "incorrect"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


def test_registration_rate_limit_is_enforced(client: TestClient) -> None:
    for index in range(5):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"new-{index}@example.test",
                "display_name": "New User",
                "password": "Correct-Horse-Battery-9!",
            },
        )
        assert response.status_code == 201

    limited = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sixth@example.test",
            "display_name": "New User",
            "password": "Correct-Horse-Battery-9!",
        },
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
