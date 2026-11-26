from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import DatabaseManager
from app.models.lead import Lead
from tests.conftest import DEFAULT_DEALER_ID, OTHER_DEALER_ID


def test_create_lead_sets_defaults_and_location_header(client: TestClient) -> None:
    payload = {
        "first_name": "Amelia",
        "last_name": "Clarke",
        "email": "amelia.clarke@example.co.uk",
        "phone": "+447700900456",
        "source": "DEALER_WEBSITE",
        "vehicle_of_interest": "2025 Volvo EX30 Twin Motor",
        "enquiry_notes": "Looking to book a weekend test drive.",
    }
    response = client.post("/api/v1/leads", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["dealership_id"] == str(DEFAULT_DEALER_ID)
    assert data["status"] == "NEW"
    assert data["last_contacted_at"] is None
    assert data["version"] == 1
    assert data["created_at"].endswith("Z")
    assert data["updated_at"].endswith("Z")
    assert response.headers["location"] == f"/api/v1/leads/{data['id']}"


def test_lead_inbox_filtering_searching_sorting_and_pagination(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead1 = create_lead(
        first_name="Oliver",
        last_name="Bennett",
        email="oliver@example.co.uk",
        source="DEALER_WEBSITE",
        vehicle_of_interest="2025 Audi Q4 e-tron",
        assigned_to="sarah@dealer.co.uk",
    )
    lead2 = create_lead(
        first_name="Liam",
        last_name="Patel",
        email="liam@example.co.uk",
        source="AUTO_TRADER",
        vehicle_of_interest="2024 BMW 320i M Sport",
        assigned_to="marcus@dealer.co.uk",
    )
    lead3 = create_lead(
        first_name="Sophie",
        last_name="Williams",
        email="sophie@example.co.uk",
        source="DEALER_WEBSITE",
        vehicle_of_interest="2025 VW ID.4",
        assigned_to="sarah@dealer.co.uk",
    )
    # Create lead in another dealership — must not appear in default inbox
    create_lead(
        first_name="George",
        last_name="Walker",
        email="george@other.co.uk",
        headers={"X-Dealer-ID": str(OTHER_DEALER_ID)},
    )

    # Transition lead1 to CONTACTED via activity so we can test multi-status filtering
    act_resp = client.post(
        f"/api/v1/leads/{lead1['id']}/activities",
        json={
            "activity_type": "CALL",
            "summary": "Initial call",
            "performed_by": "sarah@dealer.co.uk",
            "occurred_at": "2026-11-23T10:00:00Z",
        },
    )
    assert act_resp.status_code == 201

    # 1. Default inbox returns only default dealership's 3 leads
    inbox = client.get("/api/v1/leads?page=1&page_size=2")
    assert inbox.status_code == 200
    body = inbox.json()
    assert len(body["items"]) == 2
    assert body["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total_items": 3,
        "total_pages": 2,
        "has_next": True,
        "has_previous": False,
    }

    # 2. Comma-separated and repeatable status filter
    by_status = client.get("/api/v1/leads?status=CONTACTED")
    assert [item["id"] for item in by_status.json()["items"]] == [lead1["id"]]

    by_multi = client.get("/api/v1/leads?status=NEW,CONTACTED")
    assert by_multi.json()["pagination"]["total_items"] == 3

    # 3. Source + assigned_to filters
    by_source = client.get(
        "/api/v1/leads?source=AUTO_TRADER&assigned_to=marcus@dealer.co.uk"
    )
    assert [item["id"] for item in by_source.json()["items"]] == [lead2["id"]]

    # 4. Case-insensitive search on vehicle and full name
    by_vehicle = client.get("/api/v1/leads?search=audi q4")
    assert [item["id"] for item in by_vehicle.json()["items"]] == [lead1["id"]]

    by_name = client.get("/api/v1/leads?search=sophie williams")
    assert [item["id"] for item in by_name.json()["items"]] == [lead3["id"]]

    # 5. SLA triage sort: last_contacted_at ASC puts NULLs (untouched leads) first
    sla_sort = client.get(
        "/api/v1/leads?sort_by=last_contacted_at&sort_order=asc"
    )
    items = sla_sort.json()["items"]
    assert items[0]["last_contacted_at"] is None
    assert items[1]["last_contacted_at"] is None
    assert items[2]["id"] == lead1["id"]


def test_get_lead_detail_404_for_missing_wrong_tenant_or_soft_deleted(
    client: TestClient,
    db_manager: DatabaseManager,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # Non-existent UUID -> 404 RFC 7807
    missing_id = uuid4()
    resp_missing = client.get(f"/api/v1/leads/{missing_id}")
    assert resp_missing.status_code == 404
    assert resp_missing.headers["content-type"].startswith("application/problem+json")
    assert resp_missing.json()["type"].endswith("/lead-not-found")

    # Wrong dealership -> 404 RFC 7807 (multi-tenant isolation)
    resp_other_tenant = client.get(
        f"/api/v1/leads/{lead['id']}",
        headers={"X-Dealer-ID": str(OTHER_DEALER_ID)},
    )
    assert resp_other_tenant.status_code == 404
    assert resp_other_tenant.headers["content-type"].startswith("application/problem+json")

    # Soft-deleted lead -> excluded from inbox & returns 404 on detail
    with db_manager.session_factory() as session:
        row = session.get(Lead, UUID(lead["id"]))
        assert row is not None
        row.deleted_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

    assert client.get(f"/api/v1/leads/{lead['id']}").status_code == 404
    assert client.get("/api/v1/leads").json()["pagination"]["total_items"] == 0


def test_patch_lead_happy_path_and_optimistic_lock_conflict(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    assert lead["version"] == 1

    # Valid PATCH transitions NEW -> CONTACTED and increments version to 2
    patch_ok = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={
            "version": 1,
            "status": "CONTACTED",
            "assigned_to": "marcus.reed@keyloop-dealer.co.uk",
        },
    )
    assert patch_ok.status_code == 200
    updated = patch_ok.json()
    assert updated["status"] == "CONTACTED"
    assert updated["assigned_to"] == "marcus.reed@keyloop-dealer.co.uk"
    assert updated["version"] == 2

    # Stale version (1) must trigger 409 Conflict (Optimistic Lock)
    patch_conflict = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 1, "status": "QUALIFIED"},
    )
    assert patch_conflict.status_code == 409
    assert patch_conflict.headers["content-type"].startswith("application/problem+json")
    problem = patch_conflict.json()
    assert problem["type"].endswith("/optimistic-lock-conflict")
    assert problem["status"] == 409


def test_patch_lead_invalid_status_transition_returns_409(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # NEW -> CONVERTED directly is disallowed by lifecycle state machine
    resp = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 1, "status": "CONVERTED"},
    )
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["type"].endswith("/invalid-status-transition")

    # Re-opening LOST -> CONTACTED is explicitly permitted
    lost_resp = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 1, "status": "LOST"},
    )
    assert lost_resp.status_code == 200
    reopen_resp = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 2, "status": "CONTACTED"},
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "CONTACTED"


def test_lead_validation_errors_return_422_rfc7807(client: TestClient) -> None:
    # Invalid email and source enum
    resp = client.post(
        "/api/v1/leads",
        json={
            "first_name": "Bad",
            "last_name": "Email",
            "email": "not-an-email",
            "source": "INVALID_SOURCE",
        },
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["type"].endswith("/validation-error")
    assert body["status"] == 422
    fields = {e["field"] for e in body["errors"]}
    assert "body.email" in fields
    assert "body.source" in fields

    # Out-of-range pagination and invalid status query parameter
    resp_page = client.get("/api/v1/leads?page_size=250")
    assert resp_page.status_code == 422
    assert resp_page.headers["content-type"].startswith("application/problem+json")

    resp_status = client.get("/api/v1/leads?status=BOGUS")
    assert resp_status.status_code == 422
    assert resp_status.json()["errors"][0]["field"] == "query.status"
