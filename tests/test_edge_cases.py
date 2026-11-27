"""Edge-case tests added after a review of TEST_SPEC.md.

The review found gaps in the original suite: most status transition pairs were
untested, dealership isolation and soft deletion were checked on only some
endpoints, and several input edge cases had no coverage.

Tests marked ``xfail`` document known open points (SYSTEM_DESIGN.md, Section
8.5). They are expected to fail today. ``strict=True`` means that once the gap
is fixed, the test will report an unexpected pass so the marker gets removed.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.enums import ActivityType, LeadStatus
from app.core.exceptions import InvalidStatusTransitionError
from app.db.session import DatabaseManager
from app.models.lead import Lead
from app.services.activity_service import ActivityService
from app.services.lead_service import validate_status_transition
from tests.conftest import OTHER_DEALER_ID

PERFORMED_BY = "sarah.jenkins@keyloop-dealer.co.uk"

S = LeadStatus

# Expected lifecycle, written by hand from SYSTEM_DESIGN.md Section 2.1.
# Deliberately NOT imported from app.core.enums: if the code's table changes
# by mistake, this independent copy makes the tests fail.
EXPECTED_ALLOWED: dict[LeadStatus, set[LeadStatus]] = {
    S.NEW: {S.CONTACTED, S.QUALIFIED, S.TEST_DRIVE_SCHEDULED, S.NEGOTIATION, S.LOST},
    S.CONTACTED: {S.QUALIFIED, S.TEST_DRIVE_SCHEDULED, S.NEGOTIATION, S.LOST},
    S.QUALIFIED: {S.TEST_DRIVE_SCHEDULED, S.NEGOTIATION, S.LOST},
    S.TEST_DRIVE_SCHEDULED: {S.NEGOTIATION, S.CONVERTED, S.LOST},
    S.NEGOTIATION: {S.CONVERTED, S.LOST},
    S.LOST: {S.CONTACTED},
    S.CONVERTED: set(),
}

ALL_PAIRS = [(current, target) for current in LeadStatus for target in LeadStatus]


def _soft_delete(db_manager: DatabaseManager, lead_id: str) -> None:
    with db_manager.session_factory() as session:
        row = session.get(Lead, UUID(lead_id))
        assert row is not None
        row.deleted_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()


def _log_activity(
    client: TestClient, lead_id: str, **overrides: Any
) -> Any:
    payload = {
        "activity_type": "CALL",
        "summary": "Follow-up call",
        "performed_by": PERFORMED_BY,
        **overrides,
    }
    return client.post(f"/api/v1/leads/{lead_id}/activities", json=payload)


# ---------------------------------------------------------------------------
# 1. Full status transition matrix (all 49 pairs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "target"),
    ALL_PAIRS,
    ids=[f"{c.value}->{t.value}" for c, t in ALL_PAIRS],
)
def test_every_status_transition_matches_the_design(
    current: LeadStatus, target: LeadStatus
) -> None:
    should_allow = current == target or target in EXPECTED_ALLOWED[current]

    if should_allow:
        validate_status_transition(current, target)
    else:
        with pytest.raises(InvalidStatusTransitionError):
            validate_status_transition(current, target)


def test_status_change_activity_never_auto_transitions() -> None:
    for status in LeadStatus:
        assert (
            ActivityService._resolve_next_status(
                current_status=status,
                activity_type=ActivityType.STATUS_CHANGE,
                explicit_override=None,
            )
            == status
        )


def test_status_change_activity_via_api_keeps_new_lead_new(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = _log_activity(client, lead["id"], activity_type="STATUS_CHANGE")
    assert resp.status_code == 201
    assert resp.json()["lead_snapshot"]["status"] == "NEW"
    assert resp.json()["lead_snapshot"]["last_contacted_at"] is None


# ---------------------------------------------------------------------------
# 2. Dealership isolation on every lead endpoint
# ---------------------------------------------------------------------------


def test_patch_lead_from_other_dealership_returns_404_and_changes_nothing(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = client.patch(
        f"/api/v1/leads/{lead['id']}",
        json={"version": 1, "status": "LOST"},
        headers={"X-Dealer-ID": str(OTHER_DEALER_ID)},
    )
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")

    unchanged = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert unchanged["status"] == "NEW"
    assert unchanged["version"] == 1


def test_activity_feed_from_other_dealership_returns_404(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    assert _log_activity(client, lead["id"]).status_code == 201

    resp = client.get(
        f"/api/v1/leads/{lead['id']}/activities",
        headers={"X-Dealer-ID": str(OTHER_DEALER_ID)},
    )
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_inbox_of_other_dealership_does_not_show_lead(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    create_lead()
    resp = client.get("/api/v1/leads", headers={"X-Dealer-ID": str(OTHER_DEALER_ID)})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert resp.json()["pagination"]["total_items"] == 0


# ---------------------------------------------------------------------------
# 3. Soft-deleted leads on every lead endpoint
# ---------------------------------------------------------------------------


def test_soft_deleted_lead_cannot_be_patched(
    client: TestClient,
    db_manager: DatabaseManager,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    _soft_delete(db_manager, lead["id"])

    resp = client.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": 1, "status": "CONTACTED"}
    )
    assert resp.status_code == 404


def test_soft_deleted_lead_cannot_receive_activities(
    client: TestClient,
    db_manager: DatabaseManager,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    _soft_delete(db_manager, lead["id"])

    assert _log_activity(client, lead["id"]).status_code == 404


def test_soft_deleted_lead_activity_feed_returns_404(
    client: TestClient,
    db_manager: DatabaseManager,
    create_lead: Callable[..., dict[str, Any]],
) -> None:
    lead = create_lead()
    assert _log_activity(client, lead["id"]).status_code == 201
    _soft_delete(db_manager, lead["id"])

    assert client.get(f"/api/v1/leads/{lead['id']}/activities").status_code == 404


# ---------------------------------------------------------------------------
# 4. Dates and time zones (occurred_at)
# ---------------------------------------------------------------------------


def test_occurred_at_with_timezone_offset_is_converted_to_utc(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    # 18:30 in Bangkok (UTC+07:00) is 11:30 UTC
    resp = _log_activity(client, lead["id"], occurred_at="2026-11-26T18:30:00+07:00")
    assert resp.status_code == 201
    assert resp.json()["activity"]["occurred_at"] == "2026-11-26T11:30:00Z"
    assert resp.json()["lead_snapshot"]["last_contacted_at"] == "2026-11-26T11:30:00Z"


def test_occurred_at_without_timezone_is_rejected(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = _log_activity(client, lead["id"], occurred_at="2026-11-26T18:30:00")
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "body.occurred_at"


def test_occurred_at_in_the_future_is_rejected(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
    resp = _log_activity(client, lead["id"], occurred_at=future)
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "body.occurred_at"


def test_occurred_at_slightly_ahead_of_server_clock_is_accepted(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    # A client device clock running 1 minute fast must not block a real activity.
    lead = create_lead()
    ahead = (datetime.now(UTC) + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    resp = _log_activity(client, lead["id"], occurred_at=ahead)
    assert resp.status_code == 201


@pytest.mark.xfail(
    strict=True,
    reason="Open point (Section 8.5): occurred_at before the lead existed is not validated.",
)
def test_occurred_at_before_lead_creation_is_rejected(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = _log_activity(client, lead["id"], occurred_at="2000-01-01T09:00:00Z")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 5. Editing a lead (PATCH)
# ---------------------------------------------------------------------------


def test_patch_without_version_returns_422(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = client.patch(f"/api/v1/leads/{lead['id']}", json={"status": "CONTACTED"})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_patch_with_version_ahead_of_current_returns_409(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = client.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": 99, "status": "CONTACTED"}
    )
    assert resp.status_code == 409

    unchanged = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert unchanged["status"] == "NEW"
    assert unchanged["version"] == 1


def test_patch_to_same_status_is_accepted_and_keeps_status(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    resp = client.patch(f"/api/v1/leads/{lead['id']}", json={"version": 1, "status": "NEW"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "NEW"


def test_patch_backward_transition_via_api_returns_409(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    lead = create_lead()
    first = client.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": 1, "status": "QUALIFIED"}
    )
    assert first.status_code == 200

    backward = client.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": 2, "status": "CONTACTED"}
    )
    assert backward.status_code == 409
    assert backward.json()["type"].endswith("/invalid-status-transition")


# ---------------------------------------------------------------------------
# 6. Lead Inbox query edge cases
# ---------------------------------------------------------------------------


def test_inbox_page_beyond_last_returns_empty_list(
    client: TestClient, create_lead: Callable[..., dict[str, Any]]
) -> None:
    create_lead()
    resp = client.get("/api/v1/leads?page=5&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["pagination"]["total_items"] == 1
    assert body["pagination"]["has_next"] is False


@pytest.mark.parametrize(
    "query",
    ["page=0", "page_size=0", "sort_by=bogus_field", "sort_order=sideways"],
)
def test_inbox_invalid_query_parameters_return_422(client: TestClient, query: str) -> None:
    resp = client.get(f"/api/v1/leads?{query}")
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("wildcard", ["%", "_", "%%", "__"])
def test_inbox_search_treats_sql_wildcards_as_literal_text(
    client: TestClient, create_lead: Callable[..., dict[str, Any]], wildcard: str
) -> None:
    create_lead()  # no name, email or vehicle contains % or _
    resp = client.get("/api/v1/leads", params={"search": wildcard})
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total_items"] == 0
