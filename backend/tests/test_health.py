from fastapi.testclient import TestClient
from app.api.routes import health
from app.main import app

client = TestClient(app)


def test_liveness_is_independent_of_database(monkeypatch) -> None:
    monkeypatch.setattr(health, "database_is_ready", lambda: False)
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_returns_success_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr(health, "database_is_ready", lambda: True)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_service_unavailable_when_database_is_down(monkeypatch) -> None:
    monkeypatch.setattr(health, "database_is_ready", lambda: False)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["dependency"] == "database"
