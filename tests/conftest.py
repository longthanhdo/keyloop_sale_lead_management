from collections.abc import Callable, Generator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import DatabaseManager, init_db
from app.main import create_app

DEFAULT_DEALER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_DEALER_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        environment="test",
        log_level="INFO",
        default_dealership_id=DEFAULT_DEALER_ID,
    )


@pytest.fixture()
def db_manager(test_settings: Settings) -> Generator[DatabaseManager, None, None]:
    manager = DatabaseManager(test_settings)
    init_db(manager.engine)
    yield manager
    manager.dispose()


@pytest.fixture()
def app(test_settings: Settings, db_manager: DatabaseManager) -> FastAPI:
    return create_app(settings=test_settings, db_manager=db_manager)


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def create_lead(client: TestClient) -> Callable[..., dict[str, Any]]:
    def _create_lead(
        *,
        first_name: str = "Oliver",
        last_name: str = "Bennett",
        email: str = "oliver.bennett@example.co.uk",
        phone: str | None = "+447700900123",
        source: str = "DEALER_WEBSITE",
        vehicle_of_interest: str | None = "2025 Audi Q4 e-tron 45 S Line",
        enquiry_notes: str | None = "Interested in PCP finance.",
        assigned_to: str | None = "sarah.jenkins@keyloop-dealer.co.uk",
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "source": source,
            "vehicle_of_interest": vehicle_of_interest,
            "enquiry_notes": enquiry_notes,
            "assigned_to": assigned_to,
        }
        response = client.post("/api/v1/leads", json=payload, headers=headers or {})
        assert response.status_code == 201, response.text
        return response.json()

    return _create_lead
