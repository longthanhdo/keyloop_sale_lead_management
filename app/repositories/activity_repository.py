from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import SortOrder
from app.models.activity import Activity


class ActivityRepository:
    """Append-only data access layer for Activity records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, activity: Activity) -> Activity:
        self.session.add(activity)
        self.session.flush()
        return activity

    def list_for_lead(
        self,
        *,
        lead_id: UUID,
        activity_sort: SortOrder = SortOrder.ASC,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Activity], int]:
        count_stmt = select(func.count(Activity.id)).where(
            Activity.lead_id == lead_id
        )
        total_items = int(self.session.execute(count_stmt).scalar_one())

        if activity_sort == SortOrder.DESC:
            ordering = (
                Activity.occurred_at.desc(),
                Activity.created_at.desc(),
                Activity.id.desc(),
            )
        else:
            ordering = (
                Activity.occurred_at.asc(),
                Activity.created_at.asc(),
                Activity.id.asc(),
            )

        stmt = (
            select(Activity)
            .where(Activity.lead_id == lead_id)
            .order_by(*ordering)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        items = list(self.session.execute(stmt).scalars().all())
        return items, total_items
