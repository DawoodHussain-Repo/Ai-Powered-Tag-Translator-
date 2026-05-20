from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check_returns_200() -> None:
    """GET /api/v1/health returns 200 with {"status": "ok"}."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_content_type() -> None:
    """GET /api/v1/health returns application/json content type."""
    response = client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]
