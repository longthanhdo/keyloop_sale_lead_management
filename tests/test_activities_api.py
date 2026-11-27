from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.conftest import OTHER_DEALER_ID


@pytest.mark.parametrize(
    "activity_type",
    ["CALL", "EMAIL", "SMS", "QUOTE_SENT", "MEETING"],
)
def test_outreach_activity_on_new_lead_auto_transitions_to_contacted(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
    activity_type: str,
) -> None:
    lead = create_lead()
    occurred = "2026-11-23T10:15:00Z"

    resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": activity_type,
            "summary": f"Logged {activity_type} follow-up",
            "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
            "occurred_at": occurred,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["activity"]["activity_type"] == activity_type
    assert body["activity"]["occurred_at"] == occurred
    assert body["lead_snapshot"]["status"] == "CONTACTED"
    assert body["lead_snapshot"]["last_contacted_at"] == occurred
    assert body["lead_snapshot"]["version"] == 2


def test_test_drive_activity_auto_advances_non_terminal_lead(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "TEST_DRIVE_SCHEDULED",
            "summary": "Booked Saturday 11:00 test drive",
            "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
            "outcome": "BOOKED",
            "occurred_at": "2026-11-23T14:00:00Z",
        },
    )
    assert resp.status_code == 201
    snapshot = resp.json()["lead_snapshot"]
    assert snapshot["status"] == "TEST_DRIVE_SCHEDULED"
    assert snapshot["last_contacted_at"] == "2026-11-23T14:00:00Z"
    assert snapshot["version"] == 2


def test_note_activity_does_not_change_status_or_last_contacted_at(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # Log NOTE on a NEW lead: status stays NEW and last_contacted_at stays None
    note_resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "NOTE",
            "summary": "Internal valuation check",
            "notes": "CAP valuation £14,500",
            "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
        },
    )
    assert note_resp.status_code == 201
    snapshot = note_resp.json()["lead_snapshot"]
    assert snapshot["status"] == "NEW"
    assert snapshot["last_contacted_at"] is None
    assert snapshot["version"] == 2

    # Log CALL -> sets last_contacted_at, then log another NOTE -> last_contacted_at preserved
    call_time = "2026-11-23T10:00:00Z"
    call_resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "CALL",
            "summary": "Spoke with customer",
            "performed_by": "sarah.jenkins@keyloop-dealer.co.uk",
            "occurred_at": call_time,
        },
    )
    assert call_resp.status_code == 201
    assert call_resp.json()["lead_snapshot"]["last_contacted_at"] == call_time

    second_note = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "NOTE",
            "summary": "Manager review note",
            "performed_by": "manager@keyloop-dealer.co.uk",
            "occurred_at": "2026-11-23T16:00:00Z",
        },
    )
    assert second_note.status_code == 201
    assert second_note.json()["lead_snapshot"]["last_contacted_at"] == call_time
    assert second_note.json()["lead_snapshot"]["status"] == "CONTACTED"
    assert second_note.json()["lead_snapshot"]["version"] == 4


def test_chronological_ordering_asc_desc_and_retroactive_logging(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # Log activities out of chronological order (simulating retroactive logging)
    t_middle = "2026-11-23T12:00:00Z"
    t_latest = "2026-11-23T15:00:00Z"
    t_earliest = "2026-11-23T09:30:00Z"

    a_mid = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "CALL",
            "summary": "Midday call",
            "performed_by": "sarah@dealer.co.uk",
            "occurred_at": t_middle,
        },
    ).json()["activity"]["id"]

    a_late = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "EMAIL",
            "summary": "Afternoon email",
            "performed_by": "sarah@dealer.co.uk",
            "occurred_at": t_latest,
        },
    ).json()["activity"]["id"]

    # Retroactively log an earlier call: must NOT regress last_contacted_at backwards
    retro_resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "SMS",
            "summary": "Morning welcome SMS (logged retroactively)",
            "performed_by": "sarah@dealer.co.uk",
            "occurred_at": t_earliest,
        },
    )
    assert retro_resp.status_code == 201
    a_early = retro_resp.json()["activity"]["id"]
    assert retro_resp.json()["lead_snapshot"]["last_contacted_at"] == t_latest

    # Default GET /leads/{id} returns ASC order (earliest -> middle -> latest)
    detail_asc = client.get(f"/api/v1/leads/{lead['id']}")
    assert detail_asc.status_code == 200
    assert [a["id"] for a in detail_asc.json()["activities"]] == [
        a_early,
        a_mid,
        a_late,
    ]

    # GET /leads/{id}?activity_sort=desc returns reverse chronological order
    detail_desc = client.get(f"/api/v1/leads/{lead['id']}?activity_sort=desc")
    assert detail_desc.status_code == 200
    assert [a["id"] for a in detail_desc.json()["activities"]] == [
        a_late,
        a_mid,
        a_early,
    ]

    # Paginated activity sub-resource respects ordering too
    feed = client.get(
        f"/api/v1/leads/{lead['id']}/activities?activity_sort=desc&page=1&page_size=2"
    )
    assert feed.status_code == 200
    assert [a["id"] for a in feed.json()["items"]] == [a_late, a_mid]
    assert feed.json()["pagination"]["total_items"] == 3
    assert feed.json()["pagination"]["has_next"] is True


def test_explicit_status_override_and_rollback_on_invalid_override(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # Invalid explicit override (NEW -> CONVERTED) must return 409 and NOT insert activity
    bad_resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "QUOTE_SENT",
            "summary": "Invalid direct close",
            "performed_by": "sarah@dealer.co.uk",
            "new_lead_status": "CONVERTED",
        },
    )
    assert bad_resp.status_code == 409
    assert bad_resp.headers["content-type"].startswith("application/problem+json")

    # Confirm transaction rolled back cleanly (0 activities, version still 1)
    detail = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert detail["activities"] == []
    assert detail["version"] == 1

    # Valid explicit override (NEW -> NEGOTIATION) succeeds atomically
    ok_resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "QUOTE_SENT",
            "summary": "Sent PCP finance quote",
            "performed_by": "sarah@dealer.co.uk",
            "new_lead_status": "NEGOTIATION",
        },
    )
    assert ok_resp.status_code == 201
    assert ok_resp.json()["lead_snapshot"]["status"] == "NEGOTIATION"
    assert ok_resp.json()["lead_snapshot"]["version"] == 2


def test_terminal_lead_permits_post_sale_activity_without_status_regression(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 1, "status": "NEGOTIATION"},
    )
    client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 2, "status": "CONVERTED"},
    )

    resp = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "TEST_DRIVE_SCHEDULED",
            "summary": "Post-sale handover orientation drive",
            "performed_by": "sarah@dealer.co.uk",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["lead_snapshot"]["status"] == "CONVERTED"
    assert resp.json()["lead_snapshot"]["version"] == 4


def test_activity_errors_404_and_422(
    client: TestClient,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()

    # Non-existent lead -> 404 RFC 7807
    resp_missing = client.post(
        f"/api/v1/leads/{uuid4()}/activities",
        json={
            "activity_type": "CALL",
            "summary": "Call missing lead",
            "performed_by": "sarah@dealer.co.uk",
        },
    )
    assert resp_missing.status_code == 404
    assert resp_missing.headers["content-type"].startswith("application/problem+json")

    # Wrong dealership -> 404 RFC 7807
    resp_wrong_dealer = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        headers={"X-Dealer-ID": str(OTHER_DEALER_ID)},
        json={
            "activity_type": "CALL",
            "summary": "Cross-tenant attempt",
            "performed_by": "intruder@other.co.uk",
        },
    )
    assert resp_wrong_dealer.status_code == 404

    # Invalid activity_type & blank summary -> 422 RFC 7807
    resp_invalid = client.post(
        f"/api/v1/leads/{lead['id']}/activities",
        json={
            "activity_type": "INVALID_TYPE",
            "summary": "   ",
            "performed_by": "",
        },
    )
    assert resp_invalid.status_code == 422
    assert resp_invalid.headers["content-type"].startswith("application/problem+json")
    fields = {e["field"] for e in resp_invalid.json()["errors"]}
    assert "body.activity_type" in fields
    assert "body.summary" in fields
    assert "body.performed_by" in fields
