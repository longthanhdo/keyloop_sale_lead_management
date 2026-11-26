from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.dependencies import get_db_session
from app.db.session import DatabaseManager


def test_health_live_returns_200(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert "X-Correlation-ID" in response.headers


def test_health_ready_returns_200_when_db_connected(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_health_ready_returns_503_problem_json_on_db_failure(
    app: FastAPI, client: TestClient
) -> None:
    class BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("Simulated database outage")

    def override_broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_db_session] = override_broken_session
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 503
    assert body["title"] == "Service Unavailable"
    assert body["instance"] == "/health/ready"
    assert body["correlation_id"]


def test_sqlite_foreign_keys_pragma_enabled(db_manager: DatabaseManager) -> None:
    with db_manager.session_factory() as session:
        fk_enabled = session.execute(text("PRAGMA foreign_keys;")).scalar_one()
    assert fk_enabled == 1
