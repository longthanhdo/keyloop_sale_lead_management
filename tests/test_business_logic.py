"""Direct unit & service-layer tests validating core Demand domain business logic."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event

from app.core.enums import ActivityType, LeadSource, LeadStatus, SortOrder
from app.core.exceptions import (
    InvalidStatusTransitionError,
    LeadNotFoundError,
    OptimisticLockError,
)
from app.db.session import DatabaseManager
from app.schemas.activity import ActivityCreate
from app.schemas.lead import LeadCreate, LeadUpdate
from app.services.activity_service import ActivityService
from app.services.lead_service import LeadService, validate_status_transition
from tests.conftest import DEFAULT_DEALER_ID, OTHER_DEALER_ID


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LeadStatus.NEW, LeadStatus.NEW),  # Idempotent no-op
        (LeadStatus.NEW, LeadStatus.CONTACTED),
        (LeadStatus.NEW, LeadStatus.QUALIFIED),
        (LeadStatus.NEW, LeadStatus.TEST_DRIVE_SCHEDULED),
        (LeadStatus.NEW, LeadStatus.LOST),
        (LeadStatus.CONTACTED, LeadStatus.QUALIFIED),
        (LeadStatus.QUALIFIED, LeadStatus.TEST_DRIVE_SCHEDULED),
        (LeadStatus.TEST_DRIVE_SCHEDULED, LeadStatus.NEGOTIATION),
        (LeadStatus.TEST_DRIVE_SCHEDULED, LeadStatus.CONVERTED),
        (LeadStatus.NEGOTIATION, LeadStatus.CONVERTED),
        (LeadStatus.NEGOTIATION, LeadStatus.LOST),
        (LeadStatus.LOST, LeadStatus.CONTACTED),  # Customer re-engagement
    ],
)
def test_validate_status_transition_allows_valid_paths(
    current: LeadStatus, target: LeadStatus
) -> None:
    validate_status_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (LeadStatus.NEW, LeadStatus.CONVERTED),
        (LeadStatus.CONTACTED, LeadStatus.CONVERTED),
        (LeadStatus.QUALIFIED, LeadStatus.CONVERTED),
        (LeadStatus.CONVERTED, LeadStatus.NEW),
        (LeadStatus.CONVERTED, LeadStatus.LOST),
        (LeadStatus.CONVERTED, LeadStatus.NEGOTIATION),
        (LeadStatus.LOST, LeadStatus.CONVERTED),
        (LeadStatus.LOST, LeadStatus.NEW),
        (LeadStatus.NEGOTIATION, LeadStatus.NEW),
    ],
)
def test_validate_status_transition_rejects_invalid_paths(
    current: LeadStatus, target: LeadStatus
) -> None:
    with pytest.raises(InvalidStatusTransitionError) as exc_info:
        validate_status_transition(current, target)
    assert exc_info.value.current_status == current.value
    assert exc_info.value.target_status == target.value


def test_resolve_next_status_prevents_backward_regression_on_advanced_leads() -> None:
    # Logging a routine CALL on an already QUALIFIED or NEGOTIATION lead must NOT regress it to CONTACTED
    assert (
        ActivityService._resolve_next_status(
            current_status=LeadStatus.QUALIFIED,
            activity_type=ActivityType.CALL,
            explicit_override=None,
        )
        == LeadStatus.QUALIFIED
    )
    assert (
        ActivityService._resolve_next_status(
            current_status=LeadStatus.NEGOTIATION,
            activity_type=ActivityType.TEST_DRIVE_SCHEDULED,
            explicit_override=None,
        )
        == LeadStatus.NEGOTIATION
    )
    # Terminal LOST / CONVERTED leads must stay terminal on automatic rules
    assert (
        ActivityService._resolve_next_status(
            current_status=LeadStatus.LOST,
            activity_type=ActivityType.CALL,
            explicit_override=None,
        )
        == LeadStatus.LOST
    )


def test_resolve_last_contacted_at_monotonicity_and_note_invariance() -> None:
    t1 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    t2 = t1 + timedelta(hours=2)
    t0_retroactive = t1 - timedelta(hours=3)

    # First outreach sets timestamp
    assert (
        ActivityService._resolve_last_contacted_at(
            current_last_contacted_at=None,
            activity_type=ActivityType.CALL,
            occurred_at=t1,
        )
        == t1
    )

    # Newer outreach advances timestamp
    assert (
        ActivityService._resolve_last_contacted_at(
            current_last_contacted_at=t1,
            activity_type=ActivityType.EMAIL,
            occurred_at=t2,
        )
        == t2
    )

    # Retroactive outreach with earlier occurred_at does NOT regress timestamp
    assert (
        ActivityService._resolve_last_contacted_at(
            current_last_contacted_at=t2,
            activity_type=ActivityType.SMS,
            occurred_at=t0_retroactive,
        )
        == t2
    )

    # Internal NOTE and STATUS_CHANGE never alter last_contacted_at
    assert (
        ActivityService._resolve_last_contacted_at(
            current_last_contacted_at=t2,
            activity_type=ActivityType.NOTE,
            occurred_at=t2 + timedelta(hours=5),
        )
        == t2
    )
    assert (
        ActivityService._resolve_last_contacted_at(
            current_last_contacted_at=None,
            activity_type=ActivityType.STATUS_CHANGE,
            occurred_at=t1,
        )
        is None
    )


def test_lead_service_partial_update_preserves_omitted_and_clears_explicit_null(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.session_factory() as session:
        service = LeadService(session)
        created = service.create_lead(
            dealership_id=DEFAULT_DEALER_ID,
            payload=LeadCreate(
                first_name="Oliver",
                last_name="Bennett",
                email="oliver@example.co.uk",
                phone="+447700900123",
                source=LeadSource.DEALER_WEBSITE,
                vehicle_of_interest="2025 Audi Q4 e-tron",
                assigned_to="sarah@dealer.co.uk",
            ),
        )

        # Explicitly unassign lead (assigned_to=None) while omitting vehicle_of_interest
        updated = service.update_lead(
            dealership_id=DEFAULT_DEALER_ID,
            lead_id=created.id,
            payload=LeadUpdate(version=1, assigned_to=None),
        )
        assert updated.assigned_to is None
        assert updated.vehicle_of_interest == "2025 Audi Q4 e-tron"
        assert updated.version == 2

        # Cross-tenant update raises LeadNotFoundError
        with pytest.raises(LeadNotFoundError):
            service.update_lead(
                dealership_id=OTHER_DEALER_ID,
                lead_id=created.id,
                payload=LeadUpdate(version=2, status=LeadStatus.CONTACTED),
            )

        # Stale version raises OptimisticLockError
        with pytest.raises(OptimisticLockError):
            service.update_lead(
                dealership_id=DEFAULT_DEALER_ID,
                lead_id=created.id,
                payload=LeadUpdate(version=1, status=LeadStatus.CONTACTED),
            )


def test_get_lead_detail_executes_bounded_queries_no_n_plus_one(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.session_factory() as setup_session:
        lead_svc = LeadService(setup_session)
        act_svc = ActivityService(setup_session)
        lead = lead_svc.create_lead(
            dealership_id=DEFAULT_DEALER_ID,
            payload=LeadCreate(
                first_name="Elena",
                last_name="Rostova",
                email="elena@example.co.uk",
                source=LeadSource.CARWOW,
            ),
        )
        lead_id: UUID = lead.id

        # Persist 12 activities against the lead
        base_time = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)
        for idx in range(12):
            act_svc.log_activity(
                dealership_id=DEFAULT_DEALER_ID,
                lead_id=lead_id,
                payload=ActivityCreate(
                    activity_type=ActivityType.CALL if idx % 2 == 0 else ActivityType.NOTE,
                    summary=f"Follow-up step #{idx + 1}",
                    performed_by="sarah@dealer.co.uk",
                    occurred_at=base_time + timedelta(minutes=idx * 15),
                ),
            )

    select_statements: list[str] = []

    def _count_queries(
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(db_manager.engine, "before_cursor_execute", _count_queries)
    try:
        with db_manager.session_factory() as read_session:
            detail = LeadService(read_session).get_lead_detail(
                dealership_id=DEFAULT_DEALER_ID,
                lead_id=lead_id,
                activity_sort=SortOrder.ASC,
            )
    finally:
        event.remove(db_manager.engine, "before_cursor_execute", _count_queries)

    assert len(detail.activities) == 12
    # Strictly 2 SELECT queries (1 for leads + 1 selectinload for activities), proving zero N+1
    assert len(select_statements) == 2
