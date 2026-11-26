from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.enums import LeadSortField, LeadSource, LeadStatus, SortOrder
from app.models.lead import Lead


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class LeadRepository:
    """Data access layer for Lead persistence and multi-tenant queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, lead: Lead) -> Lead:
        self.session.add(lead)
        self.session.flush()
        return lead

    def get_by_id(self, lead_id: UUID, dealership_id: UUID) -> Lead | None:
        stmt = select(Lead).where(
            Lead.id == lead_id,
            Lead.dealership_id == dealership_id,
            Lead.deleted_at.is_(None),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_id_with_activities(
        self,
        lead_id: UUID,
        dealership_id: UUID,
        activity_sort: SortOrder = SortOrder.ASC,
    ) -> Lead | None:
        """Load a lead and its activities in 2 bounded queries using selectinload."""
        stmt = (
            select(Lead)
            .options(selectinload(Lead.activities))
            .where(
                Lead.id == lead_id,
                Lead.dealership_id == dealership_id,
                Lead.deleted_at.is_(None),
            )
        )
        lead = self.session.execute(stmt).scalar_one_or_none()
        if lead is None:
            return None

        reverse = activity_sort == SortOrder.DESC
        lead.activities.sort(
            key=lambda a: (a.occurred_at, a.created_at, str(a.id)),
            reverse=reverse,
        )
        return lead

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
    ) -> tuple[list[Lead], int]:
        filters: list[Any] = [
            Lead.dealership_id == dealership_id,
            Lead.deleted_at.is_(None),
        ]

        if statuses:
            filters.append(Lead.status.in_([s.value for s in statuses]))

        if source is not None:
            filters.append(Lead.source == source.value)

        if assigned_to is not None and assigned_to.strip():
            filters.append(
                func.lower(Lead.assigned_to) == assigned_to.strip().lower()
            )

        if search is not None and search.strip():
            pattern = f"%{_escape_like(search.strip())}%"
            full_name = Lead.first_name + " " + Lead.last_name
            filters.append(
                or_(
                    Lead.first_name.ilike(pattern, escape="\\"),
                    Lead.last_name.ilike(pattern, escape="\\"),
                    full_name.ilike(pattern, escape="\\"),
                    Lead.email.ilike(pattern, escape="\\"),
                    Lead.vehicle_of_interest.ilike(pattern, escape="\\"),
                )
            )

        count_stmt = select(func.count(Lead.id)).where(*filters)
        total_items = int(self.session.execute(count_stmt).scalar_one())

        sort_column_map = {
            LeadSortField.CREATED_AT: Lead.created_at,
            LeadSortField.UPDATED_AT: Lead.updated_at,
            LeadSortField.LAST_CONTACTED_AT: Lead.last_contacted_at,
        }
        sort_col = sort_column_map[sort_by]

        if sort_by == LeadSortField.LAST_CONTACTED_AT:
            if sort_order == SortOrder.ASC:
                primary_order = sort_col.asc().nulls_first()
                tie_breaker = Lead.id.asc()
            else:
                primary_order = sort_col.desc().nulls_last()
                tie_breaker = Lead.id.desc()
        else:
            if sort_order == SortOrder.ASC:
                primary_order = sort_col.asc()
                tie_breaker = Lead.id.asc()
            else:
                primary_order = sort_col.desc()
                tie_breaker = Lead.id.desc()

        items_stmt = (
            select(Lead)
            .where(*filters)
            .order_by(primary_order, tie_breaker)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.session.execute(items_stmt).scalars().all())
        return items, total_items

    def update_with_optimistic_lock(
        self,
        *,
        lead_id: UUID,
        dealership_id: UUID,
        expected_version: int,
        values: dict[str, Any],
    ) -> bool:
        """Atomically update a lead row only if its version matches expected_version."""
        update_values = {**values, "version": expected_version + 1}
        stmt = (
            update(Lead)
            .where(
                Lead.id == lead_id,
                Lead.dealership_id == dealership_id,
                Lead.deleted_at.is_(None),
                Lead.version == expected_version,
            )
            .values(**update_values)
        )
        result = self.session.execute(stmt)
        return result.rowcount == 1
