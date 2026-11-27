import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import (
    FIRST_CONTACT_ACTIVITY_TYPES,
    OUTREACH_ACTIVITY_TYPES,
    PRE_TEST_DRIVE_STATUSES,
    TERMINAL_LEAD_STATUSES,
    ActivityType,
    LeadStatus,
    SortOrder,
)
from app.core.exceptions import LeadNotFoundError, OptimisticLockError
from app.db.base import utc_now
from app.models.activity import Activity
from app.repositories.activity_repository import ActivityRepository
from app.repositories.lead_repository import LeadRepository
from app.schemas.activity import (
    ActivityCreate,
    ActivityCreatedResponse,
    ActivityFeedResponse,
    ActivityResponse,
    LeadSnapshot,
)
from app.schemas.common import PaginationMeta
from app.services.lead_service import validate_status_transition

logger = logging.getLogger("app.services.activity")


class ActivityService:
    """Domain service managing append-only activity logging and atomic lead state sync."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.lead_repo = LeadRepository(session)
        self.activity_repo = ActivityRepository(session)

    @staticmethod
    def _resolve_next_status(
        *,
        current_status: LeadStatus,
        activity_type: ActivityType,
        explicit_override: LeadStatus | None,
    ) -> LeadStatus:
        """Compute next lead status according to System Design Section 2.1."""
        if explicit_override is not None:
            validate_status_transition(current_status, explicit_override)
            return explicit_override

        # Internal notes and manual status-change logs do not force auto-transitions
        if activity_type in (ActivityType.NOTE, ActivityType.STATUS_CHANGE):
            return current_status

        # Terminal leads (CONVERTED, LOST) allow retrospective logs without status regression
        if current_status in TERMINAL_LEAD_STATUSES:
            return current_status

        # Booking a test drive advances any pre-test-drive lead automatically
        if (
            activity_type == ActivityType.TEST_DRIVE_SCHEDULED
            and current_status in PRE_TEST_DRIVE_STATUSES
        ):
            return LeadStatus.TEST_DRIVE_SCHEDULED

        # First substantive outreach on a NEW lead transitions it to CONTACTED
        if (
            activity_type in FIRST_CONTACT_ACTIVITY_TYPES
            and current_status == LeadStatus.NEW
        ):
            return LeadStatus.CONTACTED

        return current_status

    @staticmethod
    def _resolve_last_contacted_at(
        *,
        current_last_contacted_at: datetime | None,
        activity_type: ActivityType,
        occurred_at: datetime,
    ) -> datetime | None:
        """Update last_contacted_at only for outreach activities, preserving the latest timestamp."""
        if activity_type not in OUTREACH_ACTIVITY_TYPES:
            return current_last_contacted_at
        if current_last_contacted_at is None or occurred_at > current_last_contacted_at:
            return occurred_at
        return current_last_contacted_at

    def log_activity(
        self,
        *,
        dealership_id: UUID,
        lead_id: UUID,
        payload: ActivityCreate,
    ) -> ActivityCreatedResponse:
        """Atomically persist a new activity and synchronize parent lead state."""
        try:
            lead = self.lead_repo.get_by_id(
                lead_id=lead_id, dealership_id=dealership_id
            )
            if lead is None:
                self.session.rollback()
                raise LeadNotFoundError(lead_id)

            now = utc_now()
            occurred_at = payload.occurred_at or now
            current_status = LeadStatus(lead.status)

            next_status = self._resolve_next_status(
                current_status=current_status,
                activity_type=payload.activity_type,
                explicit_override=payload.new_lead_status,
            )
            next_last_contacted_at = self._resolve_last_contacted_at(
                current_last_contacted_at=lead.last_contacted_at,
                activity_type=payload.activity_type,
                occurred_at=occurred_at,
            )

            activity = Activity(
                lead_id=lead.id,
                activity_type=payload.activity_type.value,
                summary=payload.summary,
                notes=payload.notes,
                performed_by=payload.performed_by,
                outcome=payload.outcome,
                occurred_at=occurred_at,
                created_at=now,
            )
            self.activity_repo.create(activity)

            updated = self.lead_repo.update_with_optimistic_lock(
                lead_id=lead.id,
                dealership_id=dealership_id,
                expected_version=lead.version,
                values={
                    "status": next_status.value,
                    "last_contacted_at": next_last_contacted_at,
                    "updated_at": now,
                },
            )
            if not updated:
                self.session.rollback()
                raise OptimisticLockError(
                    lead_id=lead.id, expected_version=lead.version
                )

            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(lead)

        logger.info(
            "activity.logged",
            extra={
                "event": "activity.logged",
                "lead_id": str(lead.id),
                "activity_id": str(activity.id),
                "activity_type": activity.activity_type,
                "status": lead.status,
                "version": lead.version,
            },
        )

        return ActivityCreatedResponse(
            activity=ActivityResponse.model_validate(activity),
            lead_snapshot=LeadSnapshot.model_validate(lead),
        )

    def list_activities(
        self,
        *,
        dealership_id: UUID,
        lead_id: UUID,
        activity_sort: SortOrder = SortOrder.ASC,
        page: int = 1,
        page_size: int = 20,
    ) -> ActivityFeedResponse:
        lead = self.lead_repo.get_by_id(lead_id=lead_id, dealership_id=dealership_id)
        if lead is None:
            raise LeadNotFoundError(lead_id)

        activities, total_items = self.activity_repo.list_for_lead(
            lead_id=lead_id,
            activity_sort=activity_sort,
            page=page,
            page_size=page_size,
        )
        return ActivityFeedResponse(
            items=[ActivityResponse.model_validate(a) for a in activities],
            pagination=PaginationMeta.from_query(
                page=page,
                page_size=page_size,
                total_items=total_items,
            ),
        )
