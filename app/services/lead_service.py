import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import (
    ALLOWED_STATUS_TRANSITIONS,
    LeadSortField,
    LeadSource,
    LeadStatus,
    SortOrder,
)
from app.core.exceptions import (
    InvalidStatusTransitionError,
    LeadNotFoundError,
    OptimisticLockError,
)
from app.db.base import utc_now
from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.schemas.common import PaginationMeta
from app.schemas.lead import (
    LeadCreate,
    LeadDetailResponse,
    LeadInboxItem,
    LeadInboxResponse,
    LeadResponse,
    LeadUpdate,
)

logger = logging.getLogger("app.services.lead")


def validate_status_transition(
    current_status: LeadStatus, target_status: LeadStatus
) -> None:
    """Enforce the lead lifecycle transition graph (System Design Section 2.1)."""
    if current_status == target_status:
        return
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, frozenset())
    if target_status not in allowed:
        raise InvalidStatusTransitionError(
            current_status=current_status.value,
            target_status=target_status.value,
        )


class LeadService:
    """Domain service orchestrating Lead Inbox queries, creation, details, and updates."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.lead_repo = LeadRepository(session)

    def list_leads(
        self,
        *,
        dealership_id: UUID,
        statuses: Sequence[LeadStatus] | None = None,
        source: LeadSource | None = None,
        assigned_to: str | None = None,
        search: str | None = None,
        sort_by: LeadSortField = LeadSortField.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
        page: int = 1,
        page_size: int = 20,
    ) -> LeadInboxResponse:
        leads, total_items = self.lead_repo.list_leads(
            dealership_id=dealership_id,
            statuses=statuses,
            source=source,
            assigned_to=assigned_to,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        return LeadInboxResponse(
            items=[LeadInboxItem.model_validate(lead) for lead in leads],
            pagination=PaginationMeta.from_query(
                page=page,
                page_size=page_size,
                total_items=total_items,
            ),
        )

    def create_lead(
        self, *, dealership_id: UUID, payload: LeadCreate
    ) -> LeadResponse:
        now = utc_now()
        lead = Lead(
            dealership_id=dealership_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email),
            phone=payload.phone,
            source=payload.source.value,
            status=LeadStatus.NEW.value,
            vehicle_of_interest=payload.vehicle_of_interest,
            enquiry_notes=payload.enquiry_notes,
            assigned_to=payload.assigned_to,
            last_contacted_at=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        try:
            self.lead_repo.create(lead)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        logger.info(
            "lead.created",
            extra={
                "event": "lead.created",
                "lead_id": str(lead.id),
                "source": lead.source,
                "status": lead.status,
                "version": lead.version,
            },
        )
        return LeadResponse.model_validate(lead)

    def get_lead_detail(
        self,
        *,
        dealership_id: UUID,
        lead_id: UUID,
        activity_sort: SortOrder = SortOrder.ASC,
    ) -> LeadDetailResponse:
        lead = self.lead_repo.get_by_id_with_activities(
            lead_id=lead_id,
            dealership_id=dealership_id,
            activity_sort=activity_sort,
        )
        if lead is None:
            raise LeadNotFoundError(lead_id)

        return LeadDetailResponse.model_validate(lead)

    def update_lead(
        self,
        *,
        dealership_id: UUID,
        lead_id: UUID,
        payload: LeadUpdate,
    ) -> LeadResponse:
        lead = self.lead_repo.get_by_id(lead_id=lead_id, dealership_id=dealership_id)
        if lead is None:
            raise LeadNotFoundError(lead_id)

        if lead.version != payload.version:
            raise OptimisticLockError(
                lead_id=lead_id, expected_version=payload.version
            )

        update_values: dict[str, Any] = {}
        provided_fields = payload.model_fields_set

        if "status" in provided_fields and payload.status is not None:
            current_status = LeadStatus(lead.status)
            validate_status_transition(current_status, payload.status)
            update_values["status"] = payload.status.value

        non_nullable_fields = ("first_name", "last_name", "email")
        for field_name in non_nullable_fields:
            if field_name in provided_fields:
                value = getattr(payload, field_name)
                if value is not None:
                    update_values[field_name] = str(value)

        nullable_fields = (
            "phone",
            "vehicle_of_interest",
            "enquiry_notes",
            "assigned_to",
        )
        for field_name in nullable_fields:
            if field_name in provided_fields:
                update_values[field_name] = getattr(payload, field_name)

        update_values["updated_at"] = utc_now()

        try:
            updated = self.lead_repo.update_with_optimistic_lock(
                lead_id=lead_id,
                dealership_id=dealership_id,
                expected_version=payload.version,
                values=update_values,
            )
            if not updated:
                self.session.rollback()
                raise OptimisticLockError(
                    lead_id=lead_id, expected_version=payload.version
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        self.session.refresh(lead)

        logger.info(
            "lead.updated",
            extra={
                "event": "lead.updated",
                "lead_id": str(lead.id),
                "status": lead.status,
                "version": lead.version,
                "updated_fields": sorted(update_values.keys()),
            },
        )
        return LeadResponse.model_validate(lead)
